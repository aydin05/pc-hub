from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_setting

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    auth_enabled = get_setting('auth_enabled', '0')
    if auth_enabled != '1':
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        pin = request.form.get('pin', '')
        stored_pin = get_setting('auth_pin', '1234')
        if pin == stored_pin:
            session['authenticated'] = True
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash('Invalid PIN', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('auth.login'))
