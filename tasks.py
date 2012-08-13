# coding: utf-8
import simplejson as json
from celery.task import task
import github3
import redis
from sensitive import credentials
from utils import lru_cache, IN_PRODUCTION
import re
from urlparse import urlparse
from pprint import pprint
import requests
from base64 import b64encode
from pymongo import Connection
import string
from celeryconfig import QUERY_DELAY
from dateutil.parser import parse as parse_dt
from pytz import utc

#pool = redis.ConnectionPool(host=url.hostname, port=url.port, db=0, password=url.password)
pool = redis.ConnectionPool()
red = redis.StrictRedis(connection_pool=pool)
mongo = Connection(safe=True).waves

GITHUB_TIMELINE = 'https://github.com/timeline.json'
KEY_EXPIRE = 120
GRAVATAR_SIZE = 140
CUBE_COLLECTOR = 'http://localhost:1080/1.0/event/put'
with open('default_gravatar.png') as f:
    DEFAULT_GRAVATAR = f.read()

gh = github3.GitHub()
gh.login(*credentials)

class Event(object):
    '''used to render the JSON object received from GitHub's API into something that's nice to look at'''
    def __init__(self, event):
        self.__dict__.update(event)

        try:
            self.gravatar_id = self.actor_attributes['gravatar_id']
        except AttributeError:
            self.gravatar_id = ''
        try:
            self.username =  self.actor_attributes.get('name', self.actor_attributes['login'])
        except AttributeError:
            self.username = 'Anonymous'
        try:
            self.fullname = urlparse(self.repository['url']).path.strip('/') 
            self.lang = self.repository.get('language','')
        except AttributeError:
            self.fullname = ''
            self.lang = ''
            
        # avoid naming conflict with cube down the road
        self.typ = self.type
        del self.type
        
        self.template = '<a href="#">%s</a>'
        self.query_delay = QUERY_DELAY
        self.url_path = urlparse(self.url).path.strip('/')
        self.url_parts = self.url_path.strip('/').split('/')

        self.highlight = ['fullname', 'username', 'subject']
        self.utc = parse_dt(self.created_at).astimezone(utc).isoformat()
        
        self.rendered = ''
        self.render()

    def render(self):
        template_string = getattr(self, self.typ)()
        # turn them into html now
        for attr in self.highlight:
            if hasattr(self, attr):
                setattr(self, attr, self.template % getattr(self, attr))
        try:
            # TODO: properly handle utf-8
            self.rendered = unicode(template_string).format(**self.__dict__)
        except Exception, e:
            print self.__dict__
            raise

    @property
    def json(self):
        '''the json that is pushed to the client'''
        return json.dumps(self.__dict__)

    def request_gravatar(self):
        data = get_gravatar(self.gravatar_id)
        self.got_img = bool(data)
        if not self.got_img:
            data = DEFAULT_GRAVATAR
        self.img = b64encode(data)

    #///////////////// EVENT TEMPLATES /////////////////

    def WatchEvent(self):
        return '{username} started watching {fullname}'

    def CommitCommentEvent(self):
        return '{username} commented on {fullname}'
    
    def DeleteEvent(self):
        return '{username} deleted {payload[ref_type]} {payload[ref]} at {fullname}'
    
    def FollowEvent(self):
        self.subject = self.payload['target']['login']
        return '{username} started following {subject}'

    def GistEvent(self):
        self.action = {'update':'updated',
                  'fork':'forked',
                  'create':'created'}[self.payload['action']]
        return '{username} {action} Gist {payload[id]}'

    def IssueCommentEvent(self):
        self.id = re.search('/(\d+)', self.url).group(1)
        return '{username} commented on issue #{id} at {fullname}'

    def MemberEvent(self):
        return '{username} {payload[action]} {payload[member][login]} to {fullname}'

    def PullRequestEvent(self):
        self.id = self.url_parts[-1]
        return '{username} opened pull request #{id} on {fullname}'

    def PushEvent(self):
        self.branch = self.payload['ref'].split('/')[-1]
        return '{username} pushed to {branch} at {fullname}'
    
    def CreateEvent(self):
        if self.payload['ref_type'] == 'repository':
            # apparently cant rely on self.repository
            self.subject = self.url_parts[1] if self.url_parts[0] == self.username else self.url_path
            return '{username} created repository {subject}'
        return '{username} created {payload[ref_type]} {payload[ref]} at {fullname}'

    def DownloadEvent(self):
        return '{username} uploaded a file to {fullname}'

    def ForkEvent(self):
        return '{username} forked {fullname}'

    def GollumEvent(self):
        return '{username} created the {fullname} wiki'
    
    def IssuesEvent(self):
        return '{username} opened issue #{payload[number]} on {fullname}'
    
    def PublicEvent(self):
        return '{username} open sourced {fullname}'

    def PullRequestReviewCommentEvent(self):
        return '{username} commented on {fullname}'

    def WatchEvent(self):
        return '{username} started watching {fullname}'

@task
def get_events():
    queried = [Event(d) for d in gh._get(GITHUB_TIMELINE)]
    # de-dupe w/ own string render on redis
    p = red.pipeline()
    for event in queried:
        p.setnx(event.rendered, '')
    events = [event for event, not_in_redis in zip(queried, p.execute())
              if event.rendered and not_in_redis]
    
    for i, event in enumerate(events):
        print `event.rendered`
        event.i = i
        event.len_events = len(events)
        event.request_gravatar()
        red.publish("all", event.json)
    persist.delay(events)

@task
def persist(events):
    '''do data persistence on stuff that is nice-to-have but not critical
    for base functionality (stream events into redis)'''
    if not events:
        # mongo requires non-empty list
        return
    p = red.pipeline()
    pushed = p.incr('pushed', len(events))
    # so redis doesnt fill up
    for event in events:
        p.expire(event.rendered, KEY_EXPIRE)
    p.execute()
    # throw it into cube for later analysis
    data = json.dumps([{'time': e.utc
                        'type': 'gh',
                        'data':e.__dict__} for e in events])
    r = requests.post(CUBE_COLLECTOR, data=data)
    r.raise_for_status()

@task
@lru_cache(maxsize=300)
def get_gravatar(id):
    r = requests.get('http://www.gravatar.com/avatar/{id}?s={size}&d={default}'.format(id=id, size=GRAVATAR_SIZE, default=404))
    if r.ok:
        return r.content
