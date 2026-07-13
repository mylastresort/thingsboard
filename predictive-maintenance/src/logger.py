#
# Copyright © 2016-2024 The Thingsboard Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Global logger for the entire predictive maintenance service.
Import this module to use the shared logger instance across all files.

Usage:
    from src.logger import logger
    
    logger.info("This is an info message")
    logger.warning("This is a warning")
    logger.error("This is an error")
"""

import logging
import os
import sys
import warnings

# Suppress Python warnings
warnings.filterwarnings("ignore")

# Suppress TensorFlow/ML framework logs
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Get log level from environment variable (default to INFO to show info, warning, error, critical)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = level_map.get(LOG_LEVEL, logging.INFO)

# Configure root logging with better formatting
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,  # Force reconfiguration if already configured
)

# Create the global logger instance
logger = logging.getLogger("predictive_maintenance")
logger.setLevel(log_level)

# Ensure the logger propagates to root and has a handler
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Suppress noisy third-party loggers
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("absl").setLevel(logging.ERROR)
logging.getLogger("tensorflow").setLevel(logging.ERROR)
logging.getLogger("h5py").setLevel(logging.ERROR)

# Log initialization
logger.debug(f"Global logger initialized with level: {LOG_LEVEL}")
