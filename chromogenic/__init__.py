import logging, os
import atmosphere, threepio
LOGGING_LEVEL = logging.DEBUG
DEP_LOGGING_LEVEL = logging.WARN  # Logging level for dependencies.
LOG_FILENAME = os.path.abspath(os.path.join(
    os.path.dirname(atmosphere.__file__),
    '..',
    'logs/chromogenic.log'))
threepio.initialize("chromogenic",
                    log_filename=LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL)

