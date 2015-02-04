import urllib.parse
import urllib.request
import json
import os
import re
import collections
from flask import jsonify, flash, render_template


class GroupAnalyse:
    """
    Object meant for analysis of Facebook groups' content
    data: dict: for storing Facebook's response
    access_token: str: access token obtained from Facebook
    graph_url: str: base url for Graph API calls
    """

    def __init__(self):
        """
        Sets up variables
        :return: None
        """
        self.data = {}
        self.graph_url = 'https://graph.facebook.com/v2.2/'
        self.error = False
        self.error_message = ''

    def read(self, path: str, params={}, all_comments=True, all_likes=True):
        """
        Reads posts from given path and stores them into self.data
        :param path: Graph node ID
        :param params: Graph API parameters as str or dict; For example, limit or since
        :param all_comments: fetch full comments' list if needed
        :return: None
        """
        url = self.graph_url + path + '?'
        # Parse parameters into a str if they`re in a dict and append to url
        self.error_message += str(jsonify(params))
        if type(params) is dict:
            params = urllib.parse.urlencode(params)
        url += params
        self.data = self.fetch(url)
        if self.data is None or 'data' not in self.data:
            self.error = True
            self.error_message += '\nThe fetched data sucks'
            return False
        if all_comments:
            for i, post in enumerate(self.data['data']):
                # Make sure this post has comments
                if 'comments' in post:
                    has_more = 'next' in post['comments']['paging']
                    while has_more:
                        more_comments = self.fetch(post['comments']['paging']['next'])
                        self.data['data'][i]['comments']['data'].extend(more_comments['data'])
                        # Stop if there isn`t a new next link
                        if 'next' in more_comments['paging']:
                            post['comments']['paging']['next'] = more_comments['paging']['next']
                        else:
                            has_more = False

    def filter(self, params):
        pass

    def fetch(self, url):
        self.fetched_url = url
        try:
            response = urllib.request.urlopen(url)
            return json.loads(response.read().decode())
        except urllib.error.URLError:
            self.error = True
            self.error_message += '\nCould not connect to fb'
            self.error_message += '\n' + url
        except urllib.error.HTTPError as error:
            self.error = True
            try:
                data = json.loads(error.read().decode())
                self.error_message += data['error']['message']
            except (KeyError, ValueError):
                self.error_message += '\nRequest failed, error {} {}'.format(error.code, error.msg)

    def top_words(self, count=5, scan_posts=True, scan_comments=True, exclude_common=True):
        texts = []
        for post in self.data['data']:
            if scan_posts and 'message' in post and len(post['message'].strip()) > 3:
                texts.append(post['message'])
            if scan_comments and 'comments' in post:
                texts.extend(comment['message'] for comment in post['comments']['data'] if 'message' in comment)
        text = ' '.join(texts).lower()
        words = re.findall("[\w\-'\.]{3,}", text)
        if exclude_common:
            file = open('common_words.txt')
            common_words = set(file.read().split())
            file.close()
            words = [w for w in words if w not in common_words]
        return collections.Counter(words).most_common(count)

    def post_count(self):
        return len(self.data['data'])

    def comment_count(self):
        count = 0
        for post in self.data['data']:
            if 'comments' in post:
                count += len(post['comments']['data'])
        return count

    def count_comments(self):
        for i, post in enumerate(self.data['data']):
            if 'comments' in post:
                self.data['data'][i]['comment_count'] = len(post['comments']['data'])
            else:
                self.data['data'][i]['comment_count'] = 0

    def most_commented(self, count=3):
        self.count_comments()
        get_comment_count = lambda post: post['comment_count']
        most = sorted(self.data['data'], key=get_comment_count, reverse=True)
        return most[:count]

    def count_likes(self):
        for i, post in enumerate(self.data['data']):
            if 'likes' in post:
                self.data['data'][i]['like_count'] = len(post['likes']['data'])
            else:
                self.data['data'][i]['like_count'] = 0

    def like_count(self):
        count = 0
        for post in self.data['data']:
            if 'likes' in post:
                count += len(post['likes']['data'])
        return count

    def most_liked(self, count=3):
        self.count_likes()
        get_like_count = lambda post: post['like_count']
        most = sorted(self.data['data'], key=get_like_count, reverse=True)
        return most[:count]

def run(group_id='', params={}, ignore_cache=False):
    if 'ignore_cache' in params:
        ignore_cache = params['ignore_cache'] == '1'
    output = ''

    # if 'group_id' == '':
        # group_id = '190594157804565'
    output += json.dumps(params, indent=2)
    success = True

    ga = GroupAnalyse()
    cache_filename = 'fb_cache/' + group_id + '.txt'
    if os.path.exists(cache_filename):
        cache_file = open(cache_filename, 'r')
        # try:
        json_txt = cache_file.read()
        if len(json_txt) > 0:
            ga.data = json.loads(json_txt)
        # except:
        #     pass
        cache_file.close()
    if len(ga.data) == 0 or ignore_cache:
        ga.read(group_id + '/feed', params=params)
        if not ga.error:
            cache_file = open(cache_filename, 'w')
            cache_file.write(json.dumps(ga.data))
            cache_file.close()
    if ga.error:
        output = ga.error_message
    else:
        # output += '\n<a href="' + ga.fetch_url + '" target="_blank">graph_url</a>'
        output += '<ul>'
        for w in ga.top_words(4):
            output += '<li>'
            output += '{:<3d} - {}'.format(w[1], w[0]) + "\n"
            output += '</li>'
        output += '</ul><hr />'
        output += '\n post count = {:}'.format(ga.post_count())
        output += '\n comment count = {:}'.format(ga.comment_count())
        output += '\n like count = {:}'.format(ga.like_count())

        output += '\n most commented = '
        output += '<ul>'
        for post in ga.most_commented():
            output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['comment_count'], post['id'], post['id'])
        output += '</ul>'

        output += '\n most liked = '
        output += '<ul>'
        for post in ga.most_liked():
            output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['like_count'], post['id'], post['id'])
        output += '</ul>'

    return '<pre>'+output+'</pre>'