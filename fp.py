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
import operator
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

g_all_issues = []

# Yaml instance, opened at the beginning of main and then kept available
# globally.
g_yml_config = None
################################################################################
# Class node
################################################################################
class Node():
    """A node representing an issue in Jira"""
    def __init__(self, key, summary, issuetype):
        """Return a node containing the must have feature to be represented in a
        tree."""
        self.key = key
        self.summary = summary
        # Take care of some characters not supported in xml
        self.summary = self.summary.replace("\"", "'")
        self.summary = self.summary.replace("&", "and")
        self.issuetype = issuetype
        self.assignee = None
        self.sponsors = []
        self.description = None
        self.parent = None
        self.childrens = {}
        self.state = None
        self.color = None
        self.base_url = None

        self._indent = 0

    def __str__(self):
        s =  "%s%s: %s [%s]\n"              % (" " * self._indent, self.key, self.summary, self.issuetype)
        s += "%s     |   assignee:    %s\n" % (" " * self._indent, self.assignee)
        s += "%s     |   sponsors:    %s\n" % (" " * self._indent, ", ".join(self.sponsors))
        s += "%s     |   description: %s\n" % (" " * self._indent, self.description)
        s += "%s     |   parent:      %s\n" % (" " * self._indent, self.parent)
        s += "%s     |   state:       %s\n" % (" " * self._indent, self.state)
        s += "%s     |   url:         %s\n" % (" " * self._indent, self.get_url())
        s += "%s     |-> color:       %s\n" % (" " * self._indent, self.get_color())
        return s

    def _short_type(self):
        st = "I"
        if self.issuetype == "Epic":
            st = "E"
        elif self.issuetype == "Story":
            st = "S"
        return st

    def get_key(self):
        return self.key

    def add_assignee(self, assignee):
        self.assignee = assignee

    def get_assignee(self):
        return self.assignee

    def add_sponsor(self, sponsor):
        self.sponsors.append(sponsor)

    def get_sponsor(self, sponsor):
        return self.sponsors

    def add_description(self, description):
        self.description = description

    def get_description(self, description):
        return self.description

    def add_parent(self, key):
        self.parent = key

    def get_parent(self):
        return self.key

    def add_child(self, node):
        node.add_parent(self.key)
        self.childrens[node.key] = node

    def set_state(self, state):
        self.state = state

    def get_state(self):
        return self.state

    def set_color(self, color):
        self.color = color

    def get_color(self):
        if self.color is not None:
            return self.color

        color = "#990000" # Red
        if self.state == "In Progress":
            color = "#009900" # Green
        elif self.state in ["Blocked", "To Do"]:
            color = "#ff6600" # Orange
        return color

    def set_base_url(self, base_url):
        self.base_url = base_url

    def get_url(self):
        if self.base_url is not None:
            return self.base_url + "/browse/" + self.key
        else:
            return self.base_url

    def gen_tree(self, indent=0):
        self._indent = indent
        print(self)
        for key in self.childrens:
            self.childrens[key].gen_tree(self._indent + 4)

    def to_xml(self, indent=0):
        self._indent = indent
        # Main node
        xml_start = "%s<node LINK=\"%s\" TEXT=\"%s/%s: %s\" FOLDED=\"%s\" COLOR=\"%s\">" % \
                (" " * self._indent,
                        self.get_url(),
                        self._short_type(),
                        self.key,
                        self.summary,
                        "true" if self.issuetype == "Epic" else "false",
                        self.get_color())
        print(xml_start)

        # Info start
        xml_info_start = "%s<node TEXT=\"info\" FOLDED=\"true\" COLOR=\"#000000\">" % \
                (" " * (self._indent + 4))
        print(xml_info_start)

        # Assignee, single node
        xml_assignee = "%s<node TEXT=\"Assignee: %s\" FOLDED=\"false\" COLOR=\"#000000\"/>" % \
                (" " * (self._indent + 8),
                        self.assignee)
        print(xml_assignee)

        # Sponsors
        xml_sponsor_start = "%s<node TEXT=\"Sponsors\" FOLDED=\"false\" COLOR=\"#000000\">" % \
                (" " * (self._indent + 8))
        print(xml_sponsor_start)

        for s in self.sponsors:
            xml_sponsor = "%s<node TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\"/>" % \
                    (" " * (self._indent + 12), s)
            print(xml_sponsor)

        # Sponsors end
        xml_sponsor_end = "%s%s" % (" " * (self._indent + 8), "</node>")
        print(xml_sponsor_end)

        # Info end
        xml_info_end = "%s%s" % (" " * (self._indent + 4), "</node>")
        print(xml_info_end)

        # Recursive print all childrens
        for key in self.childrens:
            self.childrens[key].to_xml(self._indent + 4)

        # Add the closing element
        xml_end = "%s%s" % (" " * self._indent, "</node>")
        print(xml_end)

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

    parser.add_argument('--desc', required=False, action="store_true", \
            default=False, \
            help='Add description to the issues')

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

def get_color(assignee, name):
    color = ""
    if assignee is None:
        color = "#990000" # Red
    elif "In Progress" in name:
        color = "#009900" # Green
    elif "Blocked" in name:
        color = "#ff6600" # Orange
    elif "To Do" in name:
        color = "#ff6600" # Orange
    else:
        color = "#990000" # Red
    return color

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


def write_description(f, issue):
    try:
        f.write("<richcontent TYPE=\"DETAILS\" HIDDEN=\"true\"\n>")
        f.write("<html>\n<head>\n</head>\n<body>\n<p>\n")
        f.write(issue.fields.description)
    except UnicodeEncodeError:
        vprint("UnicodeEncodeError in description in %s" % str(issue))
        f.write("Unicode error in description, please go to Jira\n")
    f.write("\n</p>\n</body>\n</html>\n</richcontent>\n")



def start_new_issue_node(f, issue, folded="false", color = "#990000"):
    global g_all_issues
    issue_id = str(issue)
    summary = issue.fields.summary.replace("\"", "'")
    summary = summary.replace("&", "and")
    f.write("<node LINK=\"%s\" TEXT=\"%s\" FOLDED=\"%s\" COLOR=\"%s\">\n"
            % (g_server + "/browse/" + issue_id,
               issue_id + ": " + summary,
               folded,
               color))
    g_all_issues.append(issue_id)


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

    color = get_color(issue.fields.assignee, issue.fields.status.name)

    start_new_issue_node(f, issue, "true", color)
    write_single_story_node(f, issue)
    end_new_issue_node(f)

################################################################################
# Epics
################################################################################
def write_epic_node(f, key):
    global g_jira
    global g_args
    issue = g_jira.issue(key)

    print(str(issue) + " (Epic)")

    if "Closed" in issue.fields.status.name:
        return

    if "Resolved" in issue.fields.status.name:
        return

    color = get_color(issue.fields.assignee, issue.fields.status.name)

    start_new_issue_node(f, issue, "true", color)
    write_info_node(f, issue)

    if g_args.desc:
        write_description(f, issue)

    for i in issue.fields.issuelinks:
        if "inwardIssue" in i.raw:
            write_story_node(f, str(i.inwardIssue.key))

    end_new_issue_node(f)

################################################################################
# Initiatives
################################################################################
def write_initiative_node(f, issue):
    print(str(issue) + " (Initiative)")
    color = get_color(issue.fields.assignee, issue.fields.status.name)
    start_new_issue_node(f, issue, "false", color)
    write_info_node(f, issue)

    for i in issue.fields.issuelinks:
        if "inwardIssue" in i.raw:
            write_epic_node(f, str(i.inwardIssue.key))

    end_new_issue_node(f)

def build_epics_node(jira, epic_key, d_handled, initiative_node=None):
            ei = jira.issue(epic_key)
            if ei.fields.status.name in ["Closed", "Resolved"]:
                d_handled[str(ei.key)] = [None, ei]
                return None

            epic = Node(str(ei.key), str(ei.fields.summary), str(ei.fields.issuetype))
            epic.add_assignee(str(ei.fields.assignee))
            epic.set_state(str(ei.fields.status.name))
            sponsors = ei.fields.customfield_10101
            if sponsors is not None:
                for s in sponsors:
                    epic.add_sponsor(str(s.value))
            epic.set_base_url(g_server)

            if initiative_node is not None:
                epic.add_parent(initiative_node.get_key())
                initiative_node.add_child(epic)
            print(epic)

            # Deal with Stories
            for link in ei.fields.issuelinks:
                if "inwardIssue" in link.raw:
                    story_key = str(link.inwardIssue.key)
                    si = jira.issue(story_key)
                    if si.fields.status.name in ["Closed", "Resolved"]:
                        d_handled[str(si.key)] = [None, ei]
                        continue
                    story = Node(str(si.key), str(si.fields.summary), str(si.fields.issuetype))
                    story.add_assignee(str(si.fields.assignee))
                    story.set_state(str(si.fields.status.name))
                    #sponsors = si.fields.customfield_10101
                    #if sponsors is not None:
                    #    for s in sponsors:
                    #        story.add_sponsor(str(s.value))
                    story.set_base_url(g_server)
                    story.add_parent(epic.get_key())
                    epic.add_child(story)
                    #print(story)
                    d_handled[story.get_key()] = [story, si] # Story
            d_handled[epic.get_key()] = [epic, ei] # Epic


def build_initiatives_node(jira, issue, d_handled):
    if issue.fields.status.name in ["Closed", "Resolved"]:
        d_handled[str(issue.key)] = [None, issue]
        return None

    initiative = Node(str(issue.key), str(issue.fields.summary), str(issue.fields.issuetype))
    initiative.add_assignee(str(issue.fields.assignee))
    initiative.set_state(str(issue.fields.status.name))
    sponsors = issue.fields.customfield_10101
    if sponsors is not None:
        for s in sponsors:
            initiative.add_sponsor(str(s.value))
    initiative.set_base_url(g_server)
    print(initiative)

    # Deal with Epics
    for link in issue.fields.issuelinks:
        if "inwardIssue" in link.raw:
            epic_key = str(link.inwardIssue.key)
            build_epics_node(jira, epic_key, d_handled, initiative)

    d_handled[initiative.get_key()] = [initiative, issue] # Initiative
    return initiative

def build_initiatives_tree(jira, key, d_handled):
    jql = "project=%s AND issuetype in (Initiative)" % (key)
    initiatives = jira.search_issues(jql)

    nodes = []
    for i in initiatives:
        node = build_initiatives_node(jira, i, d_handled)
        if node is not None:
            nodes.append(node)
    return nodes

def build_orphans_tree(jira, key, d_handled):
    global g_all_issues

    jql = "project=%s" % (key)
    all_issues = jira.search_issues(jql)

    orphans_initiatives = []
    orphans_epics = []
    orphans_stories = []
    for i in all_issues:
        if str(i.key) not in d_handled:
            if i.fields.status.name in ["Closed", "Resolved"]:
                continue
            else:
                if i.fields.issuetype.name == "Initiative":
                    orphans_initiatives.append(i)
                elif i.fields.issuetype.name == "Epic":
                    orphans_epics.append(i)
                elif i.fields.issuetype.name == "Story":
                    orphans_stories.append(i)

    # Now we three list of Jira tickets not touched before
    #f.write("<node TEXT=\"Orphans\" POSITION=\"left\" FOLDED=\"false\" COLOR=\"#000000\">\n")

    # Initiative
    print("Initiatives ...")
    for i in orphans_initiatives:
        print(i)

    print("Epics ...")
    for i in orphans_epics:
        print(i)

    print("Stories ...")
    for i in orphans_stories:
        print(i)

    #f.write("\n</node>\n")

################################################################################
# Main function
################################################################################
def main(argv):
    global g_args
    global g_yml_config
    global g_config_filename
    global g_jira

    n1 = Node("SWG-1", "My issue 1", "Initiative")

    n12 = Node("SWG-12", "My issue 12", "Epic")
    n200 = Node("SWG-200", "My issue 200", "Story")
    n201 = Node("SWG-201", "My issue 201", "Story")
    n12.add_child(n200)
    n12.add_child(n201)

    n13 = Node("SWG-13", "My issue 13", "Epic")
    n13.add_assignee("Joakim")
    n13.set_state("In Progress")

    n14 = Node("SWG-14", "My issue 14", "Epic")
    n202 = Node("SWG-202", "My issue 202", "Story")
    n14.add_child(n202)
    n14.add_assignee("Joakim")
    n14.set_state("To Do")
    n14.set_color("#0000FF")
    n14.add_sponsor("STE")
    n14.add_sponsor("Arm")
    n14.add_sponsor("Hisilicon")
    n14.set_base_url(g_server)

    n1.add_child(n12)
    n1.add_child(n13)
    n1.add_child(n14)

    ##n1.gen_tree()
    #n1.to_xml()

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

    #f = open_file(key + ".mm")
    print("<map version=\"freeplane 1.6.0\">\n")
    print("<node LINK=\"%s\" TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\" LOCALIZED_STYLE_REF=\"AutomaticLayout.level.root\">\n"
        % (g_server + "/projects/" + key, key))

    d_handled = {}
    nodes = build_initiatives_tree(jira, key, d_handled)
    for n in nodes:
        n.to_xml()

    nodes = build_orphans_tree(jira, key, d_handled)

    print("\n</node>\n</map>")
    #f.close()

if __name__ == "__main__":
    main(sys.argv)
