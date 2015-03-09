import urllib.parse
import urllib.request
import urllib.error
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
        #     text += "\n" + repr(self.dump)
        return text


class FbScan:
    def __init__(self, group_id, params=None, cache_folder=None):
        """
        Sets up variables
        :return: None
        """
        self.group_id = group_id
        if params is None:
            params = {}
        self.params = params
        if cache_folder is None:
            cache_folder = os.path.dirname(os.path.abspath(__file__)) + '/fb_cache'
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

    def has_cache(self):
        return os.path.exists(self.cache_file)

    def clear_cache(self):
        try:
            os.remove(self.cache_file)
            return True
        except FileNotFoundError as e:
            return False

    def load(self, ignore_cache=False):
        loaded = False
        start_time = perf_counter()
        if not ignore_cache and self.has_cache():
            cache_file = open(self.cache_file, 'r')
            cache_content = cache_file.read()
            cache_file.close()
            cached = json.loads(cache_content)
            self.posts = cached['data']
            self.members = cached['members']
            loaded = True
        if not loaded:
            self.members = self.fetch_members()['data']
            self.posts = self.fetch(paged=True)['data']
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
            print('Wrote to file ' + self.cache_file)
        self.fetch_time = perf_counter() - start_time
        for member in self.members:
            self.members_dict[member['id']] = member
        self.separate()
        self.generate_flat()
        self.basic_count()

    def fetch(self, url=None, paged=False, container=None, limit=0):
        if url is None:
            url = self.graph_url + self.group_id + '/feed?' + urllib.parse.urlencode(self.params)
            if 'limit' in self.params and int(self.params['limit']) > 0:
                limit = int(self.params['limit'])
            else:
                limit = 50

        print('--------------\n\n'+url+'\n\n--------------')
        self.url_fetched = url
        try:
            response = urllib.request.urlopen(url).read().decode()
            self.request_count += 1
            content = json.loads(response)
            if container is not None:
                if container in content:
                    content = content[container]
                else:
                    content['data'] = []
                    content['paging'] = []
            under_limit = limit == 0 or len(content['data']) < limit
            while paged and under_limit and 'next' in content['paging']:
                next_url = content['paging']['next']
                del content['paging']['next']
                print('--------------\n\n'+next_url+'\n\n--------------')
                response = urllib.request.urlopen(next_url).read().decode()
                self.request_count += 1
                more = json.loads(response)
                content['data'].extend(more['data'])
                if 'next' in more['paging']:
                    content['paging']['next'] = more['paging']['next']
                under_limit = limit == 0 or len(content['data']) < limit
            if 0 < limit < len(content['data']):
                del content['data'][limit:]
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
            if post['from']['id'] not in self.members_dict:
                post['from']['administrator'] = False
                self.members_dict[post['from']['id']] = post['from']
                self.members.append(post['from'])
            if 'comments' in post and len(post['comments']['data']) > 0:
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

    def active_members(self, posts=True, comments=True, likes=False):
        def rule(member):
            return (posts and member['post_count'] > 0)\
                or (comments and member['comment_count'] > 0)\
                or (likes and member['like_count'] > 0)
        return list(filter(rule, self.members))

    def inactive_members_(self):
        return list(set(self.members) - set(self.active_members(likes=True)))

    @property
    def administrators(self):
        return [member for member in self.members if member['administrator']]

    @property
    def only_like(self):
        inactive = self.inactive_members()
        maybe_liked = self.inactive_members(likes=False)
        return [maybe_liked[member] for member in maybe_liked if member not in inactive]

    def commented_or_liked(self):
        inactive = self.inactive_members()
        maybe = self.inactive_members(likes=False, comments=False)
        return [maybe[member] for member in maybe if member not in inactive]

    @property
    def member_count(self):
        return len(self.members)

    def filter(self, filters):
        for option in filters:
            if option in ['time_from', 'time_to']:
                for i, post in enumerate(self.posts):
                    pass

    def posts_by(self, member_id):
        return list(filter(lambda post: post['from']['id'] == member_id, self.posts))

    def comments_by(self, member_id):
        return list(filter(lambda comment: comment['from']['id'] == member_id, self.flat_comments))

    def posts_liked_by(self, member_id):
        # not working yet
        def rule(post):
            return post['id'].split('_')[1] in self.likes and member_id in [like['id'] for like in self.likes[post['id']]]
        return list(filter(rule, self.posts))

    def comments_liked_by(self, member_id):
        # same here
        def rule(post):
            return post['id'] in self.likes and member_id in [like['id'] for like in self.likes[post['id']]]
        return list(filter(rule, self.flat_comments))

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

    def posts_type(self, post_type):
        """
        :param post_type: link, status, photo, video, offer
        :return:
        """
        return list(filter(lambda post: post['type'] == post_type, self.posts))

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
        if len(self.posts) == 0:
            return 0
        total_len = 0
        for post in self.posts:
            try:
                total_len += len(post['message'])
            except KeyError:
                pass
        return total_len / len(self.posts)

    @property
    def average_post_words(self):
        if len(self.posts) == 0:
            return 0
        total_len = 0
        for post in self.posts:
            try:
                total_len += len(post['message'].split())
            except KeyError:
                pass
        return total_len / len(self.posts)

    @property
    def average_comment_len(self):
        if len(self.flat_comments) == 0:
            return 0
        total_len = 0
        for comment in self.flat_comments:
            try:
                total_len += len(comment['message'])
            except KeyError:
                pass
        return total_len / len(self.flat_comments)

    @property
    def average_comment_words(self):
        if len(self.flat_comments) == 0:
            return 0
        total_len = 0
        for comment in self.flat_comments:
            try:
                total_len += len(comment['message'].split())
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

    @property
    def commented_posts(self):
        return [post for post in self.posts if post['id'] in self.comments]

    @property
    def commented_posts_count(self):
        count = 0
        for post in self.posts:
            if post['id'] in self.comments:
                count += 1
        return count

    @property
    def liked_posts(self):
        return [post for post in self.posts if post['id'] in self.likes]

    @property
    def liked_or_commented(self):
        return [post for post in self.posts if post['id'] in self.likes or post['id'] in self.comments]

    @property
    def liked_and_commented(self):
        return [post for post in self.posts if post['id'] in self.likes and post['id'] in self.comments]

    def busiest_hours(self, item='', comment_value=1, post_value=4):
        hours = {}
        for h in range(0, 24):
            hours[h] = 0
        items = [('flat_comments', comment_value), ('posts', post_value)]
        for item_type, value in items:
            if len(item) > 0 and item_type != item:
                continue
            for item in getattr(self, item_type):
                comment_time = strptime(item['created_time'][:-5], '%Y-%m-%dT%H:%M:%S')
                hours[int(comment_time.tm_hour)] += value
        return hours

    @property
    def busiest_hours_posts(self):
        return self.busiest_hours('posts')

    @property
    def busiest_hours_comments(self):
        return self.busiest_hours('flat_comments')

    @property
    def post_likes_count(self):
        return sum(post['like_count'] for post in self.posts)

    @property
    def comment_likes_count(self):
        return sum(comment['like_count'] for comment in self.flat_comments)

def work(group_id='', params={}):
    ga = FbScan(group_id, params)
    ga.clear_cache()
    ga.load(ignore_cache=True)
    return 'data fetched for group ' + group_id

def run(group_id='', params={}, ignore_cache=False):
    output = ''

    ga = FbScan(group_id, params)
    ga.load(ignore_cache)
    # output += '\n<a href="' + ga.fetch_url + '" target="_blank">graph_url</a>'
    output += '<ul>'
    for w in ga.top_words(10):
        output += '<li>'
        output += '{:<3d} - {}'.format(w[1], w[0]) + "\n"
        output += '</li>'
    output += '</ul>'
    output += '\n {:} requests in {:.3f} seconds'.format(ga.request_count, ga.fetch_time)
    output += '\n post count = {:}'.format(ga.post_count)
    lengths = [len(ga.posts_type(post_type)) for post_type in ['status', 'photo', 'video', 'link', 'event', 'offer']]
    output += '\n\tof which {:} text posts, {:} photos, {:} videos, {:} links, {:} events, {:} offers'.format(*lengths)
    commented = len(ga.commented_posts)
    liked = len(ga.liked_posts)
    liked_and_commented = len(ga.liked_and_commented)
    ignored = ga.post_count - len(ga.liked_or_commented)
    output += '\n{:} ({:.2f}%) commented posts'.format(commented, 100 * commented / ga.post_count)
    output += '\n{:} ({:.2f}%) liked posts'.format(liked, 100 * liked / ga.post_count)
    output += '\n{:} ({:.2f}%) liked and commented posts'.format(liked_and_commented, 100 * liked_and_commented / ga.post_count)
    output += '\n{:} ({:.2f}%) ignored posts'.format(ignored, 100 * ignored / ga.post_count)
    output += '\n comments per post = {:.2f}'.format(ga.comment_count / ga.post_count)
    output += '\n likes per post = {:.2f}'.format(ga.post_likes_count / ga.post_count)
    output += '\n likes per comment = {:.2f}'.format(ga.comment_likes_count / ga.comment_count)
    output += '\n comment count = {:}'.format(ga.comment_count)
    output += '\n like count = {:}'.format(ga.like_count)
    output += '\n member count = {:} (wrong if above ~4500, FB limitations)'.format(ga.member_count)
    output += '\n most recent members = <ul>' + ''.join(['<li>'+member['name']+'</li>' for member in ga.members[:3]]) + '</li>'
    active = len(ga.active_members())
    inactive = ga.member_count - len(ga.active_members(likes=True))
    output += '\n active (commented or posted) members = {:} ({:.1f}%)'.format(active, 100 * active / ga.member_count)
    output += '\n inactive members (not even liked) = {:} ({:.1f}%)'.format(inactive, 100 * inactive / ga.member_count)
    like_only = len(ga.only_like)
    output += '\n only liked something = {:} ({:.1f}%)'.format(like_only, 100 * like_only / ga.member_count)

    output += '\n average post word count = {:.2f}'.format(ga.average_post_words)
    output += '\n average comment word count = {:.2f}'.format(ga.average_comment_words)
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