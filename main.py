import os
from flask import Flask, request, jsonify, render_template
import fb

app = Flask(__name__)
app.debug = True


@app.route('/')
def index():
    return render_template('debug.html')


@app.route('/fetch', methods=['GET', 'POST'])
def fetch():
    group_id = request.args['group_id']
    args = singlify(request.args)
    del args['group_id']
    if 'spitout' in args:
        del args['spitout']
        try:
            return fb.run(group_id, args)
        except Exception as e:
            return repr(e)
    else:
        return fb.run(group_id, args)


@app.route('/workertest')
def workertest():
    from rq import Queue
    from worker import conn
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