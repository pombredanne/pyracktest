import logging


def configureLogAndThrow(filePath, throwMessage):
    logging.basicConfig(level=logging.INFO, filename=filePath)
    raise Exception(throwMessage)
