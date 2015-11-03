# -*- coding: utf-8 -*-
import logging
import httplib2
import json
import time
import random

from apiclient import errors
from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials

class OAuth():
    __services = dict()

    @staticmethod
    def getCredentials(email, scopes, client_secret, client_id):
        key = file(client_secret, 'rb')
        privateKey = key.read()
        key.close()
        credentials = SignedJwtAssertionCredentials(client_id, privateKey, scope=scopes, sub=email)
        http = httplib2.Http()
        http = credentials.authorize(http)
        credentials.refresh(http)
        return credentials, http

    @staticmethod
    def getService(email, api, version, scopes, client_secret, client_id, discoveryUrl=None):
        """
        Return the service with constant credential
        @param email: email to execute the action
        @return: the drive service
        """
        if not email.strip():
            raise Exception("OAuth.getService : Email for service is missing")

        key = email + "/" + api + "/" + version
        if key not in OAuth.__services:
            credentials, http = OAuth.getCredentials(email, scopes, client_secret, client_id)

            if discoveryUrl:
                OAuth.__services[key] = build(api, version, http=http, discoveryServiceUrl=discoveryUrl)
            else:
                OAuth.__services[key] = build(api, version, http=http)

        logging.info("OAuth.getService : Service request by - " + email)
        return OAuth.__services[key]
