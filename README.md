# db-project

## Install

### Install sys packages

    $ apt-get install sqlite3 libsqlite3-dev python-virtualenv

### Install Python packages

    $ virtualenv ve
    $ source ve/bin/activate
    $ pip install -r requirements.txt
    
### Create sqlite3 geodistance extension and initial database

    $ cd src/
    $ make
    $ python populate_db.py

### Run tests

    $ py.test
    $ sqlite3 test.sqlite -init .sqliterc < queries/r5.sql
    
## Run webapp

    $ python main.py
