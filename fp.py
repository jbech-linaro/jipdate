#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from argparse import ArgumentParser
from jira import JIRA
from jira import JIRAError
from subprocess import call
from time import gmtime, strftime

import glob
import getpass
import json
import os
import re
import sys
import unicodedata
import yaml

TEST_SERVER = 'https://dev-projects.linaro.org'
PRODUCTION_SERVER = 'https://projects.linaro.org'

# Global variables
g_config_file = None
g_config_filename = "config.yml"
g_server = PRODUCTION_SERVER
g_args = None
g_jira = None

# Yaml instance, opened at the beginning of main and then kept available
# globally.
g_yml_config = None

################################################################################
# Helper functions
################################################################################
def eprint(*args, **kwargs):
    """ Helper function that prints on stderr. """
    print(*args, file=sys.stderr, **kwargs)


def vprint(*args, **kwargs):
    """ Helper function that prints when verbose has been enabled. """
    global g_args
    if g_args.v:
        print(*args, file=sys.stdout, **kwargs)

def open_file(filename):
    """
    This will open the user provided file and if there has not been any file
    provided it will create and open a temporary file instead.
    """
    vprint("filename: %s\n" % filename)
    if filename:
        return open(filename, "w")
    else:
        return tempfile.NamedTemporaryFile(delete=False)

################################################################################
# Argument parser
################################################################################
def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to generate Freeplane mindmap files')

    parser.add_argument('-p', '--project', required=False, action="store", \
            default="SWG", \
            help='Project type (SWG, VIRT, KWG etc)')

    parser.add_argument('-t', required=False, action="store_true", \
            default=False, \
            help='Use the test server')

    parser.add_argument('-v', required=False, action="store_true", \
            default=False, \
            help='Output some verbose debugging info')

    parser.add_argument('--all', required=False, action="store_true", \
            default=False, \
            help='Load all Jira issues, not just the once marked in progress.')

    return parser

################################################################################
# Jira functions
################################################################################
def get_username_from_config():
    """ Get the username for Jira from the config file. """
    username = None
    # First check if the username is in the config file.
    try:
        username = g_yml_config['username']
    except:
        vprint("No username found in config")

    return username


def get_username_from_env():
    """ Get the username for Jira from the environment variable. """
    username = None
    try:
        username = os.environ['JIRA_USERNAME']
    except KeyError:
        vprint("No user name found in JIRA_USERNAME environment variable")

    return username


def get_username_from_input():
    """ Get the username for Jira from terminal. """
    username = raw_input("Username (john.doe@foo.org): ").lower().strip()
    if len(username) == 0:
        eprint("Empty username not allowed")
        sys.exit(os.EX_NOUSER)
    else:
        return username


def store_username_in_config(username):
    """ Append the username to the config file. """
    # Needs global variable or arg instead.
    config_file = "config.yml"
    with open(config_file, 'a') as f:
        f.write("\nusername: %s" % username)


def get_username():
    """ Main function to get the username from various places. """
    username = get_username_from_env() or \
               get_username_from_config()

    if username is not None:
        return username

    username = get_username_from_input()

    if username is not None:
        answer = raw_input("Username not found in config.yml, want to store " + \
                           "it? (y/n) ").lower().strip()
        if answer in set(['y']):
            store_username_in_config(username)
        return username
    else:
        eprint("No JIRA_USERNAME exported and no username found in config.yml")
        sys.exit(os.EX_NOUSER)


def get_password():
    """
    Get the password either from the environment variable or from the
    terminal.
    """
    try:
        password = os.environ['JIRA_PASSWORD']
        return password
    except KeyError:
        vprint("Forgot to export JIRA_PASSWORD?")

    password = getpass.getpass()
    if len(password) == 0:
        eprint("JIRA_PASSWORD not exported or empty password provided")
        sys.exit(os.EX_NOPERM)

    return password


def get_jira_instance(use_test_server):
    """
    Makes a connection to the Jira server and returns the Jira instance to the
    caller.
    """
    global g_server
    username = get_username()
    password = get_password()

    credentials=(username, password)

    if use_test_server:
        g_server = TEST_SERVER

    try:
        j = JIRA(g_server, basic_auth=credentials), username
    except JIRAError, e:
	if e.text.find('CAPTCHA_CHALLENGE') != -1:
            eprint('Captcha verification has been triggered by '\
                   'JIRA - please go to JIRA using your web '\
                   'browser, log out of JIRA, log back in '\
                   'entering the captcha; after that is done, '\
                   'please re-run the script')
            sys.exit(os.EX_NOPERM)
        else:
            raise
    return j

################################################################################
# Yaml
################################################################################
def initiate_config(config_file):
    """ Reads the config file (yaml format) and returns the sets the global
    instance.
    """
    global g_yml_config

    with open(config_file, 'r') as yml:
        g_yml_config = yaml.load(yml)

################################################################################
# Helpers
################################################################################
def sponsor_to_list(s):
    sponsors = []
    if s is not None:
        for i in s:
            sponsors.append(str(i.value))
    return sponsors

################################################################################
# General nodes
################################################################################
def write_assignee_node(f, assignee):
    f.write("<node TEXT=\"Assignee: %s\" FOLDED=\"false\" COLOR=\"#000000\"/>\n"
            % assignee)


def write_sponsor_node(f, sponsors):
    f.write("<node TEXT=\"Sponsors\" FOLDED=\"false\" COLOR=\"#000000\">\n")

    for s in sponsors:
        f.write("<node TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\"/>\n" % s)

    f.write("</node>\n")
            

def write_info_node(f, issue):
    f.write("<node TEXT=\"info\" FOLDED=\"true\" COLOR=\"#000000\">\n")
    try:
        write_assignee_node(f, issue.fields.assignee)
    except UnicodeEncodeError:
        write_assignee_node(f, "Unknown")

    try:
        write_sponsor_node(f, sponsor_to_list(issue.fields.customfield_10101))
    except AttributeError:
        vprint("No sponsor")
    f.write("</node>\n")


def start_new_issue_node(f, issue, folded="false", color = "#990000"):
    issue_id = str(issue)
    f.write("<node LINK=\"%s\" TEXT=\"%s\" FOLDED=\"%s\" COLOR=\"%s\">\n"
            % (g_server + "/browse/" + issue_id,
               issue_id + ": " + issue.fields.summary.replace("\"", "'"),
               folded,
               color))


def end_new_issue_node(f):
    f.write("</node>\n")

################################################################################
# Stories
################################################################################
def write_single_story_node(f, issue):
    f.write("<node TEXT=\"info\" FOLDED=\"true\" COLOR=\"#000000\">\n")
    try:
        write_assignee_node(f, issue.fields.assignee)
    except UnicodeEncodeError:
        write_assignee_node(f, "Unknown")
    f.write("</node>\n")


def write_story_node(f, key):
    global g_jira
    issue = g_jira.issue(key)

    print(str(issue) + " (Story)")

    if "Closed" in issue.fields.status.name:
        return

    if "Resolved" in issue.fields.status.name:
        return

    color = ""
    if issue.fields.assignee is None:
        color = "#990000" # Red
    elif "In Progress" in issue.fields.status.name:
        color = "#009900" # Green
    elif "Blocked" in issue.fields.status.name:
        color = "#ff6600" # Orange
    elif "To Do" in issue.fields.status.name:
        color = "#ff6600" # Orange
    else:
        color = "#990000" # Red

    start_new_issue_node(f, issue, "true", color)
    write_single_story_node(f, issue)
    end_new_issue_node(f)

################################################################################
# Epics
################################################################################
def write_epic_node(f, key):
    global g_jira
    issue = g_jira.issue(key)

    print(str(issue) + " (Epic)")

    if "Closed" in issue.fields.status.name:
        return

    if "Resolved" in issue.fields.status.name:
        return

    color = ""
    if issue.fields.assignee is None:
        color = "#990000" # Red
    elif "In Progress" in issue.fields.status.name:
        color = "#009900" # Green
    elif "Blocked" in issue.fields.status.name:
        color = "#ff6600" # Orange
    elif "To Do" in issue.fields.status.name:
        color = "#ff6600" # Orange
    else:
        color = "#990000" # Red

    start_new_issue_node(f, issue, "true", color)
    write_info_node(f, issue)

    for i in issue.fields.issuelinks:
        if "inwardIssue" in i.raw:
            write_story_node(f, str(i.inwardIssue.key))

    end_new_issue_node(f)

################################################################################
# Initiatives
################################################################################
def write_initiative_node(f, issue):
    print(str(issue) + " (Initiative)")
    color = ""
    if issue.fields.assignee is None:
        color = "#990000" # Red
    elif "In Progress" in issue.fields.status.name:
        color = "#009900" # Green
    elif "Blocked" in issue.fields.status.name:
        color = "#ff6600" # Orange
    elif "To Do" in issue.fields.status.name:
        color = "#ff6600" # Orange
    else:
        color = "#990000" # Red

    start_new_issue_node(f, issue, "false", color)
    write_info_node(f, issue)

    for i in issue.fields.issuelinks:
        if "inwardIssue" in i.raw:
            write_epic_node(f, str(i.inwardIssue.key))

    end_new_issue_node(f)


def get_initiatives(jira, key):
    f = open_file(key + ".mm")
    f.write("<map version=\"freeplane 1.6.0\">\n")

    f.write("<node LINK=\"%s\" TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\">\n"
        % (g_server + "/projects/" + key, key))

    jql = "project=%s AND issuetype in (Initiative)" % (key)
    initiatives = jira.search_issues(jql)

    for i in initiatives:
        issue = jira.issue(i.key)
        write_initiative_node(f, issue)

    f.write("\n</node>\n</map>")
    f.close()

################################################################################
# Main function
################################################################################
def main(argv):
    global g_args
    global g_yml_config
    global g_config_filename
    global g_jira

    # This initiates the global yml configuration instance so it will be
    # accessible everywhere after this call.
    initiate_config(g_config_filename)
    
    key = "SWG"
    parser = get_parser()

    # The parser arguments are accessible everywhere after this call.
    g_args = parser.parse_args()

    jira, username = get_jira_instance(g_args.t)
    g_jira = jira

    if g_args.project:
        key = g_args.project

    get_initiatives(jira, key)

if __name__ == "__main__":
    main(sys.argv)
