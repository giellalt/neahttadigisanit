# manage.py
# -*- encoding:utf-8 -*-

from termcolor import colored
from flask import Flask
from flask.ext.actions import Manager
from neahtta import app

manager = Manager(app, default_server_actions=True)


@manager.register('compilemessages')
def compilemessages(app):
    """ TODO: pybabel compile -d translations
    """

    def action():
        print """ You might be looking for this ...
            - pybabel compile -d translations
        """
        return False

    return action


@manager.register('makemessages')
def hello(app):
    def action():
        """ You might be looking for this ...
            - pybabel extract -F babel.cfg -k lazy_gettext -o translations/messages.pot .
            - pybabel update -i translations/messages.pot -d translations
        """
        return False

    return action


@manager.register('chk-fst-paths')
def chk_fst_paths(app):
    def get_dates(_file):
        import os.path, time
        return time.ctime(os.path.getctime(_file))

    def action():
        fsts = app.config.yaml.get('Morphology').iteritems()
        print ''
        print 'Checking config files and whether they exist...'
        missing_fst = False
        for k, v in fsts:
            file_path = ''.join(v.get('file'))
            i_file_path = ''.join(v.get('inverse_file'))
            file_exists = colored('MISSING: ', 'red')
            i_file_exists = colored('MISSING: ', 'red')
            dates = 'UPDATED: ?'
            i_dates = 'UPDATED: ?'
            try:
                with open(file_path):
                    file_exists = colored('FOUND:   ', 'green')
                    dates = 'UPDATED: %s' % get_dates(file_path)
            except IOError:
                missing_fst = True
            try:
                with open(i_file_path):
                    i_file_exists = colored('FOUND:   ', 'green')
                    i_dates = 'UPDATED: %s' % get_dates(i_file_path)
            except IOError:
                missing_fst = True

            print "%s:" % k
            print "  " + file_exists + file_path
            print "  " + dates
            print ''
            print "  " + i_file_exists + i_file_path
            print "  " + i_dates
            print ''
            print ''

        if missing_fst:
            print colored("Some FSTs were not found. See above.", "red")
        return False

    return action


if __name__ == "__main__":
    app.caching_enabled = True
    manager.run()
