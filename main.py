import os
from flask import Flask, request, jsonify, render_template
import fb
from rq import Queue
from worker import conn

app = Flask(__name__)
app.debug = True


@app.route('/')
def index(): 
    return render_template("login.html")

@app.route('/general', methods=['GET', 'POST'])
def general():
    return render_template('general.html', stats=getStats())

@app.route('/averages', methods=['GET', 'POST'])
def averages():
    return render_template('averages.html', stats=getStats())

@app.route('/users', methods=['GET', 'POST'])
def users():
    return render_template('users.html', stats=getStats())

def getStats():
    group_id = request.args['group_id']
    args = singlify(request.args)
    del args['group_id']
    
    if 'ignore_cache' in args:
        ignore_cache = args['ignore_cache'] == 'on'
        del args['ignore_cache']
    else : ignore_cache = False;
    stats = fb.FbScan(group_id, args)
    if __name__ == '__main__':
        stats.load(ignore_cache)
    else:
        try:
            stats.load(ignore_cache)
        except Exception as e:
            return repr(e)
    
    if 'spitout' in args:
        del args['spitout']
        try:
            return stats
        except Exception as e:
            return repr(e)
    else:
        return stats


@app.route('/fetch', methods=['GET', 'POST'])
def fetch():
    group_id = request.args['group_id']
    args = singlify(request.args)
    del args['group_id']
    
    if 'ignore_cache' in args:
        ignore_cache = args['ignore_cache'] == 'on'
        del args['ignore_cache']
    else:
        ignore_cache = False;
    stats = fb.FbScan(group_id, args)
    if __name__ == '__main__':
        stats.load(ignore_cache)
    else:
        try:
            stats.load(ignore_cache)
        except Exception as e:
            return repr(e)
    
    if 'spitout' in args:
        del args['spitout']
        try:
            #return render_template('stats.html', stats=stats, fb=fb)
            return fb.run(group_id, args)
        except Exception as e:
            return repr(e)
    else:
        #return render_template('stats.html', stats=stats, fb=fb)
        return fb.run(group_id, args)

@app.route('/clearcache')
def clearcache():
    ga = fb.FbScan(request.args['group_id'])
    return repr(ga.clear_cache())

@app.route('/dataready')
def dataready():
    if 'group_id' in request.args:
        stats = fb.FbScan(request.args['group_id'])
        return ['0', '1'][stats.has_cache()]
    else:
        return 'missing group_id'


@app.route('/work')
def work():
    group_id = request.args['group_id']
    args = singlify(request.args)
    del args['group_id']
    q = Queue(connection=conn)
    return repr(q.enqueue(fb.work, group_id, args))

@app.route('/wtest')
def workertest():
    import wtest
    q = Queue(connection=conn)
    result = q.enqueue(wtest.test, 'uuuu')
    return repr(result)


def singlify(args):
    splitup = dict(args)
    for k in splitup:
        if isinstance(splitup[k], list):
            if len(splitup[k]) == 1 and isinstance(splitup[k][0], str):
                splitup[k] = splitup[k][0]
    return splitup

if __name__ == '__main__':
    app.run()
