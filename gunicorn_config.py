# gunicorn_config.py

import multiprocessing

# Server socket
bind = "0.0.0.0:8005"  # Same port as before

# Worker settings
workers = multiprocessing.cpu_count() + 1  # Adjust the number of workers
worker_class = "uvicorn.workers.UvicornWorker"  # Use Uvicorn as the worker

# Logging
loglevel = "info"
accesslog = "-"  # Log to stdout (console)
errorlog = "-"   # Log to stderr (console)

# Timeout settings
timeout = 120  # Adjust the worker timeout as necessary

# Graceful timeout
graceful_timeout = 60  # Time to wait before forcefully killing workers
