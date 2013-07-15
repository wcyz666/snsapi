#-*- encoding: utf-8 -*-

'''
Renren Client

'''

if __name__ == '__main__':
    import sys
    sys.path.append('..')
    from snslog import SNSLog as logger
    from snsbase import SNSBase, require_authed
    import snstype
    from snstype import BooleanWrappedData
    import utils
else:
    from ..snslog import SNSLog as logger
    from ..snsbase import SNSBase, require_authed
    from ..snstype import BooleanWrappedData
    from .. import snstype
    from .. import utils


logger.debug("%s plugged!", __file__)

# Inteface URLs.
# This differs from other platforms
RENREN_AUTHORIZATION_URI = "http://graph.renren.com/oauth/authorize"
RENREN_ACCESS_TOKEN_URI = "http://graph.renren.com/oauth/token"
RENREN_API_SERVER = "https://api.renren.com/restserver.do"

# This error is moved back to "renren.py".
# It's platform specific and we do not expect other
# file to raise this error.
class RenrenAPIError(Exception):
    def __init__(self, code, message):
        super(RenrenAPIError, self).__init__(message)
        self.code = code

class RenrenFeedMessage(snstype.Message):
    platform = "RenrenFeed"

    def parse(self):
        self.ID.platform = self.platform
        self._parse(self.raw)

    def _parse(self, dct):
        self.ID.status_id = dct['source_id']
        self.ID.source_user_id = self.parsed.userid = str(dct['actor_id'])
        self.parsed.username = dct['name']
        self.parsed.time = utils.str2utc(dct['update_time'], " +08:00")
        self.parsed.text = ""
        self.ID.feed_type = self.parsed.feed_type = {
            10: 'STATUS',
            11: 'STATUS',
            20: 'BLOG',
            21: 'SHARE',
            22: 'BLOG',
            23: 'SHARE',
            30: 'PHOTO',
            31: 'PHOTO',
            32: 'SHARE',
            33: 'SHARE',
            34: 'OTHER',
            35: 'OTHER',
            36: 'SHARE',
            40: 'OTHER',
            41: 'OTHER',
            50: 'SHARE',
            51: 'SHARE',
            52: 'SHARE',
            53: 'SHARE',
            54: 'SHARE',
            55: 'SHARE'
        }[dct['feed_type']]
        ORIG_USER = 'orig'
        if 'attachment' in dct and dct['attachment']:
            for at in dct['attachment']:
                if 'owner_name' in at and at['owner_name']:
                    ORIG_USER = at['owner_name']
                    self.parsed.username_orig = ORIG_USER
        if 'message' in dct:
            self.parsed.text += dct['message']
        if dct['feed_type'] in [21, 23, 32, 33, 36, 50, 51, 52, 53, 54, 55]:
            self.parsed.text += u"//" + ORIG_USER + ":"
        if 'title' in dct:
            if 'message' not in dct or dct['message'] != dct['title']:
                self.parsed.text += ' "' + dct['title'] + '" '
        if 'description' in dct:
            self.parsed.text += dct['description']
        if 'attachment' in dct and dct['attachment']:
            for at in dct['attachment']:
                if at['media_type'] == 'photo':
                    self.parsed.attachments.append(
                        {
                            'type': 'picture',
                            'format': ['link'],
                            #FIXME: page photo don't have raw_src
                            'data': 'raw_src' in at and at['raw_src'] or at['src']
                        }
                    )
                elif 'href' in at:
                    #FIXME: need to do some detailed handling
                    self.parsed.attachments.append(
                        {
                            'type': 'link',
                            'format': ['link'],
                            'data': at['href']
                        })
                if 'content' in at:
                    self.parsed.text += at['content']



class RenrenStatusMessage(RenrenFeedMessage):
    platform = 'RenrenStatus'

class RenrenShareMessage(RenrenFeedMessage):
    platform = 'RenRenShare'

class RenrenBlogMessage(RenrenFeedMessage):
    platform = 'RenrenBlog'

class RenrenPhotoMessage(RenrenFeedMessage):
    platform = 'RenrenPhoto'


class RenrenFeed(SNSBase):

    Message = RenrenFeedMessage

    def __init__(self, channel = None):
        super(RenrenFeed, self).__init__(channel)
        self.platform = self.__class__.__name__

    @staticmethod
    def new_channel(full = False):
        c = SNSBase.new_channel(full)

        c['app_key'] = ''
        c['app_secret'] = ''
        c['platform'] = 'RenrenFeed'
        c['auth_info'] = {
                "save_token_file": "(default)",
                "cmd_request_url": "(default)",
                "callback_url": "http://snsapi.ie.cuhk.edu.hk/aux/auth.php",
                "cmd_fetch_code": "(default)"
                }
        return c

    def renren_request(self, method=None, **kwargs):
        '''
        A general purpose encapsulation of renren API.
        It fills in system paramters and compute the signature.
        '''

        kwargs['method'] = method
        kwargs['access_token'] = self.token.access_token
        kwargs['v'] = '1.0'
        kwargs['format'] = 'json'
        response = self._http_post(RENREN_API_SERVER, kwargs)


        if type(response) is not list and "error_code" in response:
            logger.warning(response["error_msg"])
            raise RenrenAPIError(response["error_code"], response["error_msg"])
        return response


    def auth_first(self):
        '''
        docstring placeholder
        '''

        args = {"client_id": self.jsonconf.app_key,
                "redirect_uri": self.auth_info.callback_url}
        args["response_type"] = "code"
        args["scope"] = " ".join(["read_user_feed",
                                  "read_user_status",
                                  "read_user_blog",
                                  "status_update",
                                  "publish_comment",
                                  "publish_blog"])

        url = RENREN_AUTHORIZATION_URI + "?" + self._urlencode(args)
        self.request_url(url)

    def auth_second(self):
        '''
        docstring placeholder
        '''

        try:
            url = self.fetch_code()
            self.token = self._parse_code(url)
            args = dict(client_id=self.jsonconf.app_key, redirect_uri = self.auth_info.callback_url)
            args["client_secret"] = self.jsonconf.app_secret
            args["code"] = self.token.code
            args["grant_type"] = "authorization_code"
            self.token.update(self._http_get(RENREN_ACCESS_TOKEN_URI, args))
            self.token.expires_in = self.token.expires_in + self.time()
        except Exception, e:
            logger.warning("Auth second fail. Catch exception: %s", e)
            self.token = None

    def auth(self):
        '''
        docstring placeholder
        '''

        if self.get_saved_token():
            return

        logger.info("Try to authenticate '%s' using OAuth2", self.jsonconf.channel_name)
        self.auth_first()
        self.auth_second()
        if not self.token:
            return False
        self.save_token()
        logger.debug("Authorized! access token is " + str(self.token))
        logger.info("Channel '%s' is authorized", self.jsonconf.channel_name)

    def need_auth(self):
        return True

    @require_authed
    def home_timeline(self, count=20, **kwargs):
        #FIXME: automatic paging for count > 100
        ttype='10,11,20,21,22,23,30,31,32,33,34,35,36,40,41,50,51,52,53,54,55'
        if 'type' in kwargs:
            ttype = kwargs['type']
        try:
            jsonlist = self.renren_request(
                method="feed.get",
                page=1,
                count=count,
                type=ttype,
            )
        except RenrenAPIError, e:
            logger.warning("RenrenAPIError, %s", e)
            return snstype.MessageList()

        statuslist = snstype.MessageList()
        for j in jsonlist:
            try:
                statuslist.append(self.Message(
                    j,
                    platform = self.jsonconf['platform'],
                    channel = self.jsonconf['channel_name']
                ))
            except Exception, e:
                logger.warning("Catch exception: %s", e)

        logger.info("Read %d statuses from '%s'", len(statuslist), self.jsonconf['channel_name'])
        return statuslist

    def _update_status(self, text):
        return self.renren_request(
            method='status.set',
            status = text
        ) and \
                BooleanWrappedData(True) or \
                BooleanWrappedData(False, {
                    'errors': ['PLATFORM_'],
                })


    def _update_blog(self, text, title):
        return self.renren_request(
            method='blog.addBlog',
            title=title,
            content=text
        ) and \
                BooleanWrappedData(True) or \
                BooleanWrappedData(False, {
                    'errors': ['PLATFORM_'],
                })


    def _update_share_link(self, text, link):
        return self.renren_request(
            method='share.share',
            type='6',
            url=link,
            comment=text
        ) and \
                BooleanWrappedData(True) or \
                BooleanWrappedData(False, {
                    'errors': ['PLATFORM_'],
                })


    def _dummy_update(self, text, **kwargs):
        return False

    @require_authed
    def update(self, text, **kwargs):
        coder= int(''.join(map(lambda t: str(int(t)),
            [
                'title' in kwargs,
                'link' in kwargs
            ][::-1])
        ))
        try:
            update_what = {
                0: self._update_status,
                1: self._update_blog,
                10: self._update_share_link
            }[coder]
        except:
            return BooleanWrappedData(False, {
                'errors' : ['SNSAPI_NOT_SUPPORTED'],
            })
        return update_what(text, **kwargs)

    @require_authed
    def reply(self, statusId, text):
        #NOTE: you can mix API1 and API2.
        #NOTE: API2 is more better on comment
        res = None
        if statusId.feed_type == 'STATUS':
            res = self.renren_request(
                method='status.addComment',
                status_id=statusId.status_id,
                owner_id=statusId.source_user_id,
                content=text
            )
        elif statusId.feed_type == 'SHARE':
            res = self.renren_request(
                method='share.addComment',
                share_id=statusId.status_id,
                user_id=statusId.source_user_id,
                content=text
            )
        elif statusId.feed_type == 'BLOG':
            res = self.renren_request(
                method='blog.addComment',
                id=statusId.status_id,
                #FIXME: page_id, uid
                uid=statusId.source_user_id,
                content=text
            )
        elif statusId.feed_type == 'PHOTO':
            res = self.renren_request(
                method='photos.addComment',
                uid=statusId.source_user_id,
                content=text,
                #FIXME: aid, pid
                pid=statusId.status_id
            )
        else:
            return BooleanWrappedData(False, {
                'errors' : ['SNSAPI_NOT_SUPPORTED'],
            })
        if res:
            return BooleanWrappedData(True)
        else:
            return BooleanWrappedData(False, {
                'errors' : ['PLATFORM_'],
            })

    @require_authed
    def forward(self, message, text):
        res = None
        if message.parsed.feed_type == 'STATUS':
            res = self.renren_request(
                method='status.forward',
                status=text,
                forward_id=message.ID.status_id,
                forward_owner=message.ID.source_user_id,
            )
        elif message.parsed.feed_type != 'OTHER':
            res = self.renren_request(
                method='share.share',
                type=str({
                    'BLOG': 1,
                    'PHOTO': 2,
                    'SHARE': 20
                }[message.parsed.feed_type]),
                ugc_id=message.ID.status_id,
                user_id=message.ID.source_user_id,
                comment=text
            )
        else:
            return BooleanWrappedData(False, {
                'errors' : ['SNSAPI_NOT_SUPPORTED'],
            })
        if res:
            return BooleanWrappedData(True)
        else:
            return BooleanWrappedData(False, {
                'errors' : ['PLATFORM_'],
            })


class RenrenStatus(RenrenFeed):
    Message = RenrenStatusMessage

    def __init__(self, channel=None):
        super(RenrenStatus, self).__init__(channel)

    @staticmethod
    def new_channel(full=False):
        c = RenrenFeed.new_channel(full)
        c['platform'] = 'RenrenStatus'
        return c

    @require_authed
    def home_timeline(self, count=20):
        return RenrenFeed.home_timeline(self, count, type='10,11')

    @require_authed
    def update(self, text):
        return RenrenFeed._update_status(self, text)


class RenrenBlog(RenrenFeed):
    Message = RenrenBlogMessage

    def __init__(self, channel=None):
        super(RenrenBlog, self).__init__(channel)

    @staticmethod
    def new_channel(full=False):
        c = RenrenFeed.new_channel(full)
        c['platform'] = 'RenrenBlog'
        return c

    @require_authed
    def home_timeline(self, count=20):
        return RenrenFeed.home_timeline(self, count, type='20,22')

    @require_authed
    def update(self, text, title=None):
        if not title:
            title = text.split('\n')[0]
        return RenrenFeed._update_blog(self, text, title)

class RenrenPhoto(RenrenFeed):
    Message = RenrenPhotoMessage

    def __init__(self, channel=None):
        super(RenrenPhoto, self).__init__(channel)

    @staticmethod
    def new_channel(full=False):
        c = RenrenFeed.new_channel(full)
        c['platform'] = 'RenrenPhoto'
        return c

    @require_authed
    def home_timeline(self, count=20):
        return RenrenFeed.home_timeline(self, count, type='30,31')

    @require_authed
    def update(self, text, photo=None):
        return False

class RenrenShare(RenrenFeed):
    Message = RenrenShareMessage

    def __init__(self, channel=None):
        super(RenrenShare, self).__init__(channel)

    @staticmethod
    def new_channel(full=False):
        c = RenrenFeed.new_channel(full)
        c['platform'] = 'RenrenShare'
        return c

    @require_authed
    def home_timeline(self, count=20):
        return RenrenFeed.home_timeline(self, count, type='21,23,32,33,36,50,51,52,53,54,55')

    @require_authed
    def update(self, text, link=None):
        if not link:
            link = text
        return RenrenFeed._update_share_link(self, text, link)