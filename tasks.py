# coding: utf-8
import simplejson as json
from celery.task import task, chord
from utils import lru_cache, IN_PRODUCTION
import re
from urlparse import urlparse
from pprint import pprint
import requests
from base64 import b64encode
import string
from celeryconfig import QUERY_DELAY
from dateutil.parser import parse as parse_dt
from pytz import utc
from markdown import markdown

import redis
pool = redis.ConnectionPool()
red = redis.StrictRedis(connection_pool=pool)
KEY_EXPIRE = 120
REDIS_NAME = 'waves:'
# clear out redis
for k in red.keys(REDIS_NAME + '*'):
    red.delete(k)

import github3
from sensitive import credentials
gh = github3.GitHub()
gh.login(*credentials)

ANON = '///' # placeholder that can't be a username
GITHUB_TIMELINE = 'https://github.com/timeline.json'
GRAVATAR_SIZE = 140
CUBE_COLLECTOR = 'http://localhost:1080/1.0/event/put'
with open('default_gravatar.png') as f:
    DEFAULT_GRAVATAR = f.read()

class Event(object):
    '''used to render the JSON object received from GitHub's API into something that's nice to look at'''


    def __init__(self, event):
        self.__dict__.update(event)

        self.gravatar_id = ''
        self.login = self.username = ANON
        self.fullname = ''
        self.lang = ''
        self.query_delay = QUERY_DELAY
        self.url_path = urlparse(self.url).path.strip('/')
        self.url_parts = self.url_path.strip('/').split('/')

        self.utc = parse_dt(self.created_at).astimezone(utc).isoformat()
        self.append_fullname = True
        self.prepend_username = True
        
        self.rendered = ''
        if hasattr(self, 'actor_attributes'):
            self.gravatar_id = self.actor_attributes['gravatar_id']
            self.login = self.actor_attributes['login']
            self.username = self.actor_attributes.get('name','')
            # generally avoid empty usernames
            if not self.username.strip():
                self.username = self.actor_attributes['login']
                
        if hasattr(self, 'repository'):
            self.fullname = urlparse(self.repository['url']).path.strip('/') 
            self.lang = self.repository.get('language','')
            
        # avoid naming conflict with cube down the road
        try:
            self.typ = self.type
            del self.type
        except AttributeError:
            pass # already done
        
        self.render()

    def render(self):
        '''turn the pretty bare-bones templates into full-featured HTML with URLs
        pointing to Github and whatnot'''
        # try the dict then the methods
        template_string = self.templates.get(self.typ) or getattr(self, self.typ)()
        # most templates want these things
        if self.prepend_username:
            template_string = '[{username}](/{login}) ' + template_string
        if self.append_fullname:
            template_string += ' [{fullname}](/{fullname})'
        # turn relative links into github absolute links
        template_string = template_string.replace('](/','](https://github.com/')
            
        try:
            # TODO: properly handle utf-8
            self.rendered = markdown(unicode(template_string).format(**self.__dict__))
        except Exception, e:
            print template_string
            print self.typ
            print self.__dict__
            raise

    @property
    def json(self):
        '''the json that is pushed to the client'''
        # TODO: push only whats necessary
        return json.dumps(self.__dict__)

    def request_gravatar(self):
        data = get_gravatar(self.gravatar_id)
        self.got_img = bool(data)
        if not self.got_img:
            data = DEFAULT_GRAVATAR
        self.img = b64encode(data)

    @property
    def redis_repr(self):
        '''the string that is used to de-dupe on redis'''
        return REDIS_NAME + self.rendered

    #///////////////// EVENT TEMPLATES /////////////////

    templates = {
        'WatchEvent': 'started watching',
        'CommitCommentEvent': 'commented on',
        'DeleteEvent': 'deleted {payload[ref_type]} {payload[ref]} at',
        'MemberEvent': '{payload[action]} {payload[member][login]} to',
        'PullRequestEvent': 'opened [pull request #{url_parts[3]}]({url}) on',
        'DownloadEvent': 'uploaded a file to',
        'ForkEvent': 'forked',
        'IssuesEvent': 'opened [issue #{payload[number]}]({url}) on',
        'PublicEvent': 'open sourced',
        'PullRequestReviewCommentEvent': 'commented on',
        }

    def FollowEvent(self):
        self.subject = self.payload['target']['login']
        self.append_fullname = False
        return 'started following [{subject}]({url})'

    def GistEvent(self):
        self.append_fullname = False
        self.action = {'update':'updated',
                       'fork':'forked',
                       'create':'created'}[self.payload['action']]
        template = '{action} [Gist {payload[id]}]({url})'
        if self.username == ANON:
            self.prepend_username = False
            return 'Anonymous ' + template
        return template

    def IssueCommentEvent(self):
        self.id = re.search('/(\d+)', self.url).group(1)
        return 'commented on [issue #{id}]({url}) at'

    def PushEvent(self):
        self.branch = self.payload['ref'].split('/')[-1]
        return 'pushed to {branch} at'
    
    def CreateEvent(self):
        if self.payload['ref_type'] == 'repository':
            # apparently cant rely on self.repository being there
            self.subject = self.url_parts[1] if self.url_parts[0] == self.username else self.url_path
            self.append_fullname = False
            return 'created repository [{subject}]({url})'
        return 'created {payload[ref_type]} {payload[ref]} at'

    def GollumEvent(self):
        self.append_fullname = False
        return 'created the [{fullname}](/{fullname}) wiki'

@task
def get_events():
    queried = [Event(d) for d in gh._get(GITHUB_TIMELINE).json]
    print len(queried)
    # de-dupe w/ own string representation on redis
    p = red.pipeline()
    for event in queried:
        p.setnx(event.redis_repr, '')
    events = [event for event, not_in_redis in zip(queried, p.execute())
              if event.rendered and not_in_redis]
    print len(events)
    
    for i, event in enumerate(events):
        # assign the position in list for later client-side 
        # delaying and send back into queue
        print `event.rendered`
        event.i = i
        event.len_events = len(events)
        process_event.delay(event)

@task
def process_event(event):
    '''request the gravatar'''
    event.request_gravatar()
    red.publish("all", event.json)
    persist.delay(event)
    
@task
def persist(event):
    '''do data persistence on stuff that is nice-to-have but not critical
    for base functionality (streaming events into redis)'''
    pushed = red.incr(REDIS_NAME + 'pushed')
    # so redis doesnt fill up
    red.expire(event.redis_repr, KEY_EXPIRE)
    # throw it into cube for later analysis
    data = json.dumps([{'time': event.utc,
                        'type': 'gh',
                        'data':event.__dict__}])
    r = requests.post(CUBE_COLLECTOR, data=data)
    r.raise_for_status()
    print r.ok

@task
@lru_cache(maxsize=300)
def get_gravatar(id):
    r = requests.get('http://www.gravatar.com/avatar/{id}?s={size}&d={default}'.format(id=id, size=GRAVATAR_SIZE, default=404))
    if r.ok:
        return r.content

if __name__ == '__main__':
    pass
