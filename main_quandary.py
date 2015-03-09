import os
from flask import Flask, request, jsonify, render_template
import fb

app = Flask(__name__)
app.debug = True


@app.route('/')
def index(): 
    return render_template("login.html")
    #return render_template('debug.html')


@app.route('/general', methods=['GET', 'POST'])
def general():
    return render_template('general.html', stats=getStats())

@app.route('/averages', methods=['GET', 'POST'])
def averages():
    return render_template('averages.html', stats=getStats())

@app.route('/users', methods=['GET', 'POST'])
def users():
    return render_template('users.html', stats=getStats())



@app.route('/workertest')
def workertest():
    from rq import Queue
    from worker import conn
    import wtest
    q = Queue(connection=conn)
    result = q.enqueue(wtest.test, 'uuuu')
    return repr(result)


def getStats():
    group_id = request.args['group_id']
    args = singlify(request.args)
    del args['group_id']
    
    if 'ignore_cache' in args:
        ignore_cache = args['ignore_cache'] == 'on'
        del args['ignore_cache']
    else : ignore_cache = False;
    
    stats = fb.FbScan(group_id, args)
    stats.load(ignore_cache)
    
    return stats;



def singlify(args):
    splitup = dict(args)
    for k in splitup:
        if isinstance(splitup[k], list):
            if len(splitup[k]) == 1 and isinstance(splitup[k][0], str):
                splitup[k] = splitup[k][0]
    return splitup

if __name__ == '__main__':
    app.run()
