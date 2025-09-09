# LockBot

LockBot is an IRC bot for managing resource locks. It allows users to register resources, and then lock and unlock them. This is useful in a team environment where you need to coordinate access to shared resources, like development servers or testing hardware.

## Features

*   Register and unregister resources.
*   Lock and unlock resources.
*   Try to lock a resource and fail if it's already locked (`trylock`).
*   Wait in a queue for a lock to be released (`lock`).
*   Assign a lock to another user (`assignlock`).
*   Forcefully free a lock held by another user (`freelock`).
*   List all registered resources, or just the locked or free ones.
*   Fuzzy matching of resource names to avoid typos.
*   SSL support for secure connection to the IRC server.
*   Logging via syslog.

## Usage

1.  **Install dependencies:**

    ```bash
    pip install twisted
    pip install python-Levenshtein
    ```
    `dumbdbm` is part of the Python standard library.

2.  **Configure the bot:**

    Create a configuration file (e.g., `lockbot.conf`). A sample configuration file is provided as `sample.conf`.

    ```ini
    [lockbot]
    server   = irc.example.com
    port     = 6697
    password = <server_password>
    channel  = yourchannel
    nickname = lockbot
    dbdir    = ./lockbot_db
    usessl   = yes
    ```

3.  **Run the bot:**

    ```bash
    python Main.py lockbot.conf
    ```

    The bot will connect to the specified IRC server and join the channel. The lock database will be created in the directory specified by `dbdir`.

## Commands

You can interact with the bot by sending messages in the channel or in a private message. The bot's nickname can be used to address it (e.g., `lockbot: help`).

*   **`help`**: display the help message.
*   **`register <resource1>[,<resource2>,...]`**: add one or more new resources to the database.
*   **`unregister <resource1>[,<resource2>,...]`**: remove one or more resources from the database.
*   **`lock <resource1>[,<resource2>,...]`**: try to take the lock, or get on queue if it is currently locked.
*   **`unlock <resource1>[,<resource2>,...]`**: release the resource lock.
*   **`trylock <resource1>[,<resource2>,...]`**: take hold of a lock on a resource, but fail if it's already locked.
*   **`assignlock <assignee> <resource>`**: assign a resource lock to someone else other than the caller.
*   **`freelock <resource1>[,<resource2>,...]`**: release a resource lock even if the caller does not hold the lock (USE WITH CAUTION).
*   **`status`**: list locked resources and their owners.
*   **`list`**: list all registered resources.
*   **`listfree`**: list unlocked resources.

## TODO

*   Command-line options (`--daemonize`, `--help`).
*   Daemonize the process (with an option to run in the foreground).
