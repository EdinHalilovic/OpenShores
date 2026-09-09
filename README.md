For more information, visit the [OpenShores](https://openshores.net/) website.

## Requirements
- PostgreSQL
- Python 3.13 or higher

## Installing

Download the repo and unpack it in your location of choice.

Linux:
```
python3.13 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows:
```
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Database

Create a new empty database through PGAdmin with an user with a password that has full access to it.
Open up the 'openshores.toml' and modify the 'database_url' line with your new username, password and the database name.
The server will take care of the rest during the first run generation.

## Running
After activating the venv, all you have to do is run
```
openshores
```
and the server will boot up.


## Accounts
There doesn't exist a properly tooled way of handling accounts through the CLI yet, so here are a few commands to handle the basic functions until that is properly implemented:

### Creating an account

Windows:
```
.\.venv\Scripts\python.exe -c "from openshores.core.accounts import default_store, _wire_password; default_store().create('USERNAME', _wire_password('PASSWORD'))"
```

Linux:
```
.venv/bin/python -c "from openshores.core.accounts import default_store, _wire_password; default_store().create('USERNAME', _wire_password('PASSWORD'))"
```
### Deleting an account

Windows:
```
.\.venv\Scripts\python.exe -c "from openshores.core.accounts import default_store; default_store().delete('USERNAME')"
```

Linux:
```
.venv/bin/python -c "from openshores.core.accounts import default_store; default_store().delete('USERNAME')"
```

### Changing a password

Windows:
```
.\.venv\Scripts\python.exe -c "from openshores.core.accounts import default_store, _wire_password; default_store().set_password('USERNAME', _wire_password('PASSWORD'))"
```

Linux:
```
.venv/bin/python -c "from openshores.core.accounts import default_store, _wire_password; default_store().set_password('USERNAME', _wire_password('PASSWORD'))"
```
