#!/usr/bin/python3
"""Simple Flask-based Bittrex API wrapper server."""
import os
from functools import wraps

from flask import (Flask, current_app, flash, redirect, render_template,
                   request, send_from_directory, session, url_for)
from flask_pymongo import PyMongo
from modules.bittrex import fetch
from modules.forms import LoginForm
from modules.helpers import get_report, summarize, utcdate
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'archive'
app.config['MONGO_DBNAME'] = 'bittrex'
mongo = PyMongo(app)


def login_required(f):
    """Check if user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('You have to be logged in!', category='danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def validate(form):
    """Check user data in MongoDB."""
    user = mongo.db.users.find_one({'username': form.username.data})
    if user and check_password_hash(user['password'], form.password.data):
        return True
    else:
        return False


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login procedure function."""
    if 'username' in session:
        flash('You have to log out first!', category='warning')
        return redirect(url_for(request.referrer))
    form = LoginForm()
    if request.method == 'POST':
        if validate(form):
            flash('You have successfully logged in to the website!',
                  category='success')
            session['username'] = form.username.data
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash('Please check your login credentials!',
                  category='danger')
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    """Log out from the website."""
    flash('Goodbye, {}!'.format(session['username']), category='success')
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/uploads/<path:filename>')
@login_required
def download(filename):
    """Download a single file."""
    uploads = os.path.join(current_app.root_path, app.config['UPLOAD_FOLDER'])
    return send_from_directory(directory=uploads, filename=filename)


@app.route('/')
@login_required
def index():
    """Show the main page."""
    return render_template('index.html', name=session['username'],
                           report=get_report())


@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    """Show the reports page."""
    if request.method == 'POST':
        result = fetch(request.form['from'],
                       request.form['to'],
                       request.form['coin'])
        if result:
            flash('Found {} results!'.format(
                len(result[1])), category='success')
            return render_template('report.html',
                                   name=session['username'],
                                   download=result[0],
                                   data=result[1][:100])
        else:
            flash('No results found!', category='warning')
    return render_template('report.html', name=session['username'])


@app.route('/graph', methods=['GET', 'POST'])
@login_required
def graph():
    """Show the graphs page."""
    if request.method == 'POST':
        result = summarize(int(request.form.get('interval')),
                           request.form['to'] or utcdate(),
                           request.form['coin'],
                           request.form['fast'],
                           request.form['slow'],
                           request.form['signal'])
        if result:
            flash('Found {} results!'.format(
                len(result)), category='success')
            return render_template('graph.html',
                                   name=session['username'],
                                   data=result,
                                   tovalue=request.form['to'],
                                   coinvalue=request.form['coin'],
                                   prices=[float(i['price'])
                                           for i in
                                           result
                                           ][::-1
                                             ],
                                   fastes=[float(i['ema_fast'])
                                           for i in result
                                           ][::-1
                                             ],
                                   slowes=[float(i['ema_slow'])
                                           for i in result
                                           ][::-1
                                             ],
                                   minutes='*'.join([i['datetime']
                                                     for i in result
                                                     ][::-1
                                                       ]
                                                    ),
                                   macds=[float(i['macd'])
                                           for i in result
                                          ][::-1
                                            ],
                                   macd_hists=[float(i['macd_hist'])
                                               for i in result
                                               ][::-1
                                                 ],
                                   signallines=[float(i['signal_line'])
                                                for i in result
                                                ][::-1
                                                  ],
                                   bearbull=float(result[0]['macd_hist']))
        else:
            flash('No results found!', category='warning')
    return render_template('graph.html', name=session['username'])


if __name__ == '__main__':
    app.run(debug=True)
