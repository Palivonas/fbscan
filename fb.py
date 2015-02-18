import urllib.parse
import urllib.request
import json
import os
import re
import collections
from time import strptime, perf_counter
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
            params = {}
        self.params = params
        self.cache_folder = cache_folder
        if not os.path.exists(cache_folder):
            os.mkdir(cache_folder)
        self.posts = []
        self.comments = {}
        # for holding one-level list of comments
        self.flat_comments = []
        self.likes = {}
        self.members = []
        self.members_dict = {}
        self.graph_url = 'https://graph.facebook.com/v2.2/'
        self.request_count = 0
        self.fetch_time = 0

    @property
    def cache_file(self):
        cache_id = self.group_id
        return os.path.join(self.cache_folder, cache_id + '.json')

    def load(self, ignore_cache=False):
        loaded = False
        start_time = perf_counter()
        if not ignore_cache and os.path.exists(self.cache_file):
            cache_file = open(self.cache_file, 'r')
            cache_content = cache_file.read()
            cache_file.close()
            cached = json.loads(cache_content)
            self.posts = cached['data']
            self.members = cached['members']
            loaded = True
        if not loaded:
            self.posts = self.fetch()['data']
            self.fetch_paged()
            self.fetch_comment_likes()
            self.members = self.fetch_members()['data']
            cached = {
                'data': self.posts,
                'members': self.members
            }
            cache_file = open(self.cache_file, 'w+')
            cache_file.write(json.dumps(cached))
            cache_file.close()
        self.fetch_time = perf_counter() - start_time
        self.separate()
        self.generate_flat()
        self.basic_count()
        for member in self.members:
            self.members_dict[member['id']] = member

    def fetch(self, url=None, paged=False, inside=None):
        if url is None:
            url = self.graph_url + self.group_id + '/feed?' + urllib.parse.urlencode(self.params)
        self.url_fetched = url
        try:
            response = urllib.request.urlopen(url).read().decode()
            self.request_count += 1
            content = json.loads(response)
            if inside is not None:
                content = content[inside]
            while paged and 'next' in content['paging']:
                next_url = content['paging']['next']
                del content['paging']['next']
                response = urllib.request.urlopen(next_url).read().decode()
                self.request_count += 1
                more = json.loads(response)
                content['data'].extend(more['data'])
                if 'next' in more['paging']:
                    content['paging']['next'] = more['paging']['next']
            return content
        except KeyError as error:
            raise FbScanError(error)
        except urllib.error.HTTPError as e:
            response = e.read().decode()
            message = json.loads(response)['error']['message']
            raise FbScanError(message)

    def fetch_paged(self):
        for i, post in enumerate(self.posts):
            # Make sure this post has comments or likes
            for reaction in ['likes', 'comments']:
                if reaction in post:
                    has_more = 'next' in post[reaction]['paging']
                    while has_more:
                        url = post[reaction]['paging']['next'] + '&limit=999'
                        more_comments = self.fetch(url)
                        self.posts[i][reaction]['data'].extend(more_comments['data'])
                        # Stop if there isn`t a new next link
                        if 'next' in more_comments['paging']:
                            post[reaction]['paging']['next'] = more_comments['paging']['next']
                        else:
                            has_more = False

    def fetch_comment_likes(self):
        for post in self.posts:
            if 'comments' in post:
                for comment in post['comments']['data']:
                    if comment['like_count'] > 0:
                        url = self.graph_url + '/' + post['id'] + '_' + comment['id']
                        url += '?limit=999&fields=likes&access_token=' + self.params['access_token']
                        likes = self.fetch(url, True, 'likes')['data']
                        comment['likes'] = likes

    def separate(self):
        for post in self.posts:
            if 'comments' in post:
                for comment in post['comments']['data']:
                    if 'likes' in comment:
                        self.likes[comment['id']] = comment['likes']
                        del comment['likes']
                self.comments[post['id']] = post['comments']['data']
                del post['comments']
            if 'likes' in post:
                self.likes[post['id']] = post['likes']['data']
                del post['likes']

    def generate_flat(self):
        for post_id in self.comments:
            for comment in self.comments[post_id]:
                single_comment = comment.copy()
                post_id = post_id[post_id.find('_') + 1:]
                single_comment['id'] = post_id + '_' + single_comment['id']
                self.flat_comments.append(single_comment)

    def basic_count(self):
        for post in self.posts:
            # Make sure this post has comments or likes
            for reaction, name in [(self.likes, 'like'), (self.comments, 'comment')]:
                count = 0
                if post['id'] in reaction:
                    count = len(reaction[post['id']])
                post[name + '_count'] = count

        for member in self.members:
            member['post_count'] = 0
            member['like_count'] = 0
            member['comment_count'] = 0
            for post in self.posts:
                if post['from']['id'] == member['id']:
                    member['post_count'] += 1
            for likes in self.likes.values():
                for like in likes:
                    if like['id'] == member['id']:
                        member['like_count'] += 1
            for comments in self.comments.values():
                for comment in comments:
                    if comment['from']['id'] == member['id']:
                        member['comment_count'] += 1

    def fetch_members(self):
        url = self.graph_url + self.group_id + '/members?limit=9999999&access_token=' + self.params['access_token']
        return self.fetch(url, True)

    def top_posters(self, count=5):
        sorted_members = sorted(self.members, key=lambda member: member['post_count'], reverse=True)
        return sorted_members[:count]

    def top_commenters(self, count=5):
        sorted_members = sorted(self.members, key=lambda member: member['comment_count'], reverse=True)
        return sorted_members[:count]

    def top_likers(self, count=5):
        sorted_members = sorted(self.members, key=lambda member: member['like_count'], reverse=True)
        return sorted_members[:count]

    def inactive_members(self, posts=True, comments=True, likes=True):
        members = self.members_dict.copy()
        if posts:
            for post in self.posts:
                try:
                    del members[post['from']['id']]
                except KeyError:
                    pass
        if comments:
            for comment in self.flat_comments:
                try:
                    del members[comment['from']['id']]
                except KeyError:
                    pass
        if likes:
            for likes in self.likes.values():
                for like in likes:
                    try:
                        del members[like['id']]
                    except KeyError:
                        pass
        return members

    @property
    def only_like(self):
        inactive = self.inactive_members()
        maybe_liked = self.inactive_members(likes=False)
        return [maybe_liked[member] for member in maybe_liked if member not in inactive]

    @property
    def member_count(self):
        return len(self.members)

    def filter(self, filters):
        for option in filters:
            if option in ['time_from', 'time_to']:
                for i, post in enumerate(self.posts):
                    pass

    def top_words(self, count=5, one_per_message=True, scan_posts=True, scan_comments=True, exclude_common=True):
        texts = []
        if scan_posts:
            texts.extend(post['message'] for post in self.posts if 'message' in post)
        if scan_comments:
            for comments in self.comments.values():
                texts.extend(comment['message'] for comment in comments)
        
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
        return len(self.posts)

    @property
    def comment_count(self):
        return len(self.flat_comments)

    @property
    def like_count(self):
        count = 0
        for likes in self.likes.values():
            count += len(likes)
        return count

    @property
    def average_post_len(self):
        total_len = 0
        for post in self.posts:
            try:
                total_len += len(post['message'])
            except KeyError:
                pass
        return total_len / len(self.posts)

    @property
    def average_comment_len(self):
        total_len = 0
        for comment in self.flat_comments:
            try:
                total_len += len(comment['message'])
            except KeyError:
                pass
        return total_len / len(self.flat_comments)

    def most_commented(self, count=3):
        get_comment_count = lambda post: post['comment_count']
        most = sorted(self.posts, key=get_comment_count, reverse=True)
        return most[:count]

    def most_liked_posts(self, count=3):
        get_like_count = lambda post: post['like_count']
        most = sorted(self.posts, key=get_like_count, reverse=True)
        return most[:count]

    def most_liked_comments(self, count=3):
        get_like_count = lambda comment: comment['like_count']
        most = sorted(self.flat_comments, key=get_like_count, reverse=True)
        return most[:count]

    def busiest_hours(self, item=''):
        hours = {}
        for h in range(0, 24):
            hours[h] = 0
        for items, value in [('flat_comments', 1), ('posts', 4)]:
            for item in getattr(self, items):
                comment_time = strptime(item['created_time'][:-5], '%Y-%m-%dT%H:%M:%S')
                hours[int(comment_time.tm_hour)] += value
        return hours


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
    output += '</ul>'
    output += '\n {:} requests in {:.3f} seconds'.format(ga.request_count, ga.fetch_time)
    output += '\n post count = {:}'.format(ga.post_count)
    output += '\n comment count = {:}'.format(ga.comment_count)
    output += '\n like count = {:}'.format(ga.like_count)
    output += '\n member count = {:}'.format(ga.member_count)
    inactive = len(ga.inactive_members())
    output += '\n totally inactive members = {:} ({:.1f}%)'.format(inactive, 100 * inactive / ga.member_count)
    like_only = len(ga.only_like)
    output += '\n only liked something = {:} ({:.1f}%)'.format(like_only, 100 * like_only / ga.member_count)

    output += '\n average post length = {:.2f}'.format(ga.average_post_len)
    output += '\n average comment length = {:.2f}'.format(ga.average_comment_len)
    output += '\n most commented = '
    output += '<ul>'
    for post in ga.most_commented():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['comment_count'], post['id'], post['id'])
    output += '</ul>'

    output += '\n top posters = '
    output += '<ul>'
    for member in ga.top_posters():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(member['post_count'], member['id'], member['name'])
    output += '</ul>'

    output += '\n top commenters = '
    output += '<ul>'
    for member in ga.top_commenters():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(member['comment_count'], member['id'], member['name'])
    output += '</ul>'

    output += '\n top likers = '
    output += '<ul>'
    for member in ga.top_likers():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(member['like_count'], member['id'], member['name'])
    output += '</ul>'

    output += '\n most liked posts = '
    output += '<ul>'
    for post in ga.most_liked_posts():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['like_count'], post['id'], post['id'])
    output += '</ul>'

    output += '\n most liked comments = '
    output += '<ul>'
    for post in ga.most_liked_comments():
        output += '<li>{:} - <a target="_blank" href="https://facebook.com/{:}">{:}</a></li>'.format(post['like_count'], post['id'], post['id'])
    output += '</ul>'
    output += 'bussiest hours\n'
    output += json.dumps(ga.busiest_hours(), indent=2)

    return '<pre>'+output+'</pre>'