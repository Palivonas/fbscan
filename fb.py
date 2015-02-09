import urllib.parse
import urllib.request
import json
import os
import re
import collections
from flask import jsonify, flash, render_template

class FbScanError(Exception):
    def __init__(self, value, dump=None):
        self.value = value
        self.dump = dump
    def __str__(self):
        text = repr(self.value)
        # if dump is not None:
            # text += "\n" + repr(self.dump)
        return text

class FbScan:

    def __init__(self, group_id, params=None, cache_folder='fb_cache'):
        """
        Sets up variables
        :return: None
        """
        self.group_id = group_id
        if params is None:
            params={}
        self.params = params
        self.cache_folder = cache_folder
        if not os.path.exists(cache_folder):
            os.mkdir(cache_folder)
        self.data = {}
        self.members = {}
        self.graph_url = 'https://graph.facebook.com/v2.2/'

    @property
    def cache_file(self):
        cache_id = self.group_id
        return os.path.join(self.cache_folder, cache_id + '.json')

    def load(self, ignore_cache=False):
        loaded = False
        if not ignore_cache and os.path.exists(self.cache_file):
            cache_file = open(self.cache_file, 'r')
            cache_content = cache_file.read()
            cache_file.close()
            cached = json.loads(cache_content)
            self.data = cached['data']
            self.members = cached['members']
            loaded = True
        if not loaded:
            self.data = self.fetch()['data']
            self.fetch_paged()
            self.members = self.fetch_members()['data']
            cached = {
                'data' : self.data,
                'members' : self.members
            }
            cache_file = open(self.cache_file, 'w+')
            cache_file.write(json.dumps(cached))
            cache_file.close()
        self.basic_count()

    def fetch(self, url=None, paged=False):
        if url is None:
            url = self.graph_url + self.group_id + '/feed?' + urllib.parse.urlencode(self.params)
        self.url_fetched = url
        try:
            response = urllib.request.urlopen(url).read().decode()
            content = json.loads(response)
            second = False
            while (paged or not second) and 'next' in content['paging']:
                second = True
                next_url = content['paging']['next']
                del content['paging']['next']
                response = urllib.request.urlopen(next_url).read().decode()
                more = json.loads(response)
                content['data'].extend(more['data'])
                if 'next' in more['paging']:
                    content['paging']['next'] = more['paging']['next']
            return content
        except KeyError:
            raise FbScanError('"data" not in response')
        except urllib.error.HTTPError as e:
            response = e.read().decode()
            message = json.loads(response)['error']['message']
            raise FbScanError(message)

    def fetch_paged(self):
        for i, post in enumerate(self.data):
            # Make sure this post has comments or likes
            for reaction in ['likes', 'comments']:
                if reaction in post:
                    has_more = 'next' in post[reaction]['paging']
                    while has_more:
                        url = post[reaction]['paging']['next'] + '&limit=200'
                        more_comments = self.fetch(url)
                        self.data[i][reaction]['data'].extend(more_comments['data'])
                        # Stop if there isn`t a new next link
                        if 'next' in more_comments['paging']:
                            post[reaction]['paging']['next'] = more_comments['paging']['next']
                        else:
                            has_more = False

    def basic_count(self):
        for post in self.data:
            # Make sure this post has comments or likes
            for reaction in ['likes', 'comments']:
                count = 0
                if reaction in post:
                    count = len(post[reaction]['data'])
                post[reaction[:-1] + '_count'] = count

        for member in self.members:
            member['post_count'] = 0
            member['like_count'] = 0
            member['comment_count'] = 0
            for post in self.data:
                if post['from']['id'] == member['id']:
                    member['post_count'] += 1
                if 'likes' in post:
                    for like in post['likes']['data']:
                        if like['id'] == member['id']:
                            member['like_count'] += 1
                if 'comments' in post:
                    for comment in post['comments']['data']:
                        if comment['from']['id'] == member['id']:
                            member['comment_count'] += 1

    def fetch_members(self):
        url = self.graph_url + self.group_id + '/members?limit=9999999&access_token=' + self.params['access_token']
        return self.fetch(url, True)

    def top_commenters(self, count=5):
        sorted_members = sorted(self.members, key=lambda member: member['comment_count'], reverse=True)
        return sorted_members[:count]

    @property
    def member_count(self):
        return len(self.members)
    
 
    def filter(self, params):
        pass

    def top_words(self, count=5, one_per_message=True, scan_posts=True, scan_comments=True, exclude_common=True):
        texts = []
        for post in self.data:
            if scan_posts and 'message' in post and len(post['message'].strip()) > 3:
                texts.append(post['message'])
            if scan_comments and 'comments' in post:
                texts.extend(comment['message'] for comment in post['comments']['data'] if 'message' in comment)
        
        words = []
        for text in texts:
            current_words = re.findall("[\w\-'\.]{3,}", text.lower())
            if one_per_message:
                current_words = list(set(current_words))
            words.extend(current_words)
        if exclude_common:
            file = open('common_words.txt')
            common_words = set(file.read().split())
            file.close()
            words = [w for w in words if w not in common_words]
        return collections.Counter(words).most_common(count)

    @property
    def post_count(self):
        return len(self.data)

    @property
    def comment_count(self):
        count = 0
        for post in self.data:
            if 'comments' in post:
                count += len(post['comments']['data'])
        return count

    @property
    def like_count(self):
        count = 0
        for post in self.data:
            if 'likes' in post:
                count += len(post['likes']['data'])
        return count

    def most_commented(self, count=3):
        get_comment_count = lambda post: post['comment_count']
        most = sorted(self.data, key=get_comment_count, reverse=True)
        return most[:count]

    def most_liked(self, count=3):
        get_like_count = lambda post: post['like_count']
        most = sorted(self.data, key=get_like_count, reverse=True)
        return most[:count]

def run(group_id='', params={}, ignore_cache=False):
    if 'ignore_cache' in params:
        ignore_cache = params['ignore_cache'] == 'on'
        del params['ignore_cache']
    output = ''

    # if 'group_id' == '':
        # group_id = '190594157804565'
    output += json.dumps(params, indent=2)
    success = True

    ga = FbScan(group_id, params)
    ga.load(ignore_cache)
    # output += '\n<a href="' + ga.fetch_url + '" target="_blank">graph_url</a>'
    output += '<ul>'
    for w in ga.top_words(4):
        output += '<li>'
        output += '{:<3d} - {}'.format(w[1], w[0]) + "\n"
        output += '</li>'
    output += '</ul><hr />'
    output += '\n post count = {:}'.format(ga.post_count)
    output += '\n comment count = {:}'.format(ga.comment_count)
    output += '\n like count = {:}'.format(ga.like_count)
    output += '\n member count = {:}'.format(ga.member_count)

    output += '\n most commented = '
    output += '<ul>'
    for post in ga.most_commented():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['comment_count'], post['id'], post['id'])
    output += '</ul>'

    output += '\n top commenters = '
    output += '<ul>'
    for member in ga.top_commenters():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(member['comment_count'], member['id'], member['name'])
    output += '</ul>'

    output += '\n most liked = '
    output += '<ul>'
    for post in ga.most_liked():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['like_count'], post['id'], post['id'])
    output += '</ul>'
    output += 'bussiest hours'

    return '<pre>'+output+'</pre>'