#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from argparse import ArgumentParser
from jira import JIRA
from jira import JIRAError
from subprocess import call
from time import gmtime, strftime

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
g_config_filename = "config.yml"
g_server = PRODUCTION_SERVER
g_args = None

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
        self.childrens = []
        self.state = None
        self.color = None
        self.base_url = None

        self._indent = 0
        self._sortval = 3

    def __str__(self):
        s =  "%s%s: %s [%s]\n"              % (" " * self._indent, self.key, self.summary, self.issuetype)
        s += "%s     |   sponsors:    %s\n" % (" " * self._indent, ", ".join(self.sponsors))
        s += "%s     |   assignee:    %s\n" % (" " * self._indent, self.assignee)
        s += "%s     |   description: %s\n" % (" " * self._indent, self.description)
        s += "%s     |   parent:      %s\n" % (" " * self._indent, self.parent)
        s += "%s     |   state:       %s\n" % (" " * self._indent, self.state)
        s += "%s     |   url:         %s\n" % (" " * self._indent, self.get_url())
        s += "%s     |-> color:       %s\n" % (" " * self._indent, self.get_color())
        return s

    def __lt__(self, other):
        return self._sortval < other._sortval

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
        #try:
        #    f.write("<richcontent TYPE=\"DETAILS\" HIDDEN=\"true\"\n>")
        #    f.write("<html>\n<head>\n</head>\n<body>\n<p>\n")
        #    f.write(issue.fields.description)
        #except UnicodeEncodeError:
        #    vprint("UnicodeEncodeError in description in %s" % str(issue))
        #    f.write("Unicode error in description, please go to Jira\n")
        #f.write("\n</p>\n</body>\n</html>\n</richcontent>\n")
        return self.description

    def add_parent(self, key):
        self.parent = key

    def get_parent(self):
        return self.key

    def add_child(self, node):
        node.add_parent(self.key)
        self.childrens.append(node)

    def set_state(self, state):
        self.state = state

        if self.state in ["In Progress"]:
            self._sortval = int(1)
        elif self.state in ["To Do", "Blocked"]:
            self._sortval = int(2)
        else:
            self._sortval = int(3)

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
        for c in self.childrens:
            c.gen_tree(self._indent + 4)

    def to_xml(self, f, indent=0):
        self._indent = indent
        # Main node
        xml_start = "%s<node LINK=\"%s\" TEXT=\"%s/%s: %s\" FOLDED=\"%s\" COLOR=\"%s\">\n" % \
                (" " * self._indent,
                 self.get_url(),
                 self._short_type(),
                 self.key,
                 self.summary,
                 "true" if self.issuetype in ["Epic", "Story"] else "false",
                 self.get_color())
        f.write(xml_start)

        # Info start
        xml_info_start = "%s<node TEXT=\"info\" FOLDED=\"true\" COLOR=\"#000000\">\n" % \
                (" " * (self._indent + 4))
        f.write(xml_info_start)

        # Assignee, single node
        xml_assignee = "%s<node TEXT=\"Assignee: %s\" FOLDED=\"false\" COLOR=\"#000000\"/>\n" % \
                (" " * (self._indent + 8),
                        self.assignee)
        f.write(xml_assignee)

        # Sponsors
        xml_sponsor_start = "%s<node TEXT=\"Sponsors\" FOLDED=\"false\" COLOR=\"#000000\">\n" % \
                (" " * (self._indent + 8))
        f.write(xml_sponsor_start)

        for s in self.sponsors:
            xml_sponsor = "%s<node TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\"/>\n" % \
                    (" " * (self._indent + 12), s)
            f.write(xml_sponsor)

        # Sponsors end
        xml_sponsor_end = "%s%s" % (" " * (self._indent + 8), "</node>\n")
        f.write(xml_sponsor_end)

        # Info end
        xml_info_end = "%s%s" % (" " * (self._indent + 4), "</node>\n")
        f.write(xml_info_end)

        # Recursive print all childrens
        for c in sorted(self.childrens):
            c.to_xml(f, self._indent + 4)

        # Add the closing element
        xml_end = "%s%s" % (" " * self._indent, "</node>\n")
        f.write(xml_end)


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

def get_parent_key(jira, issue):
    if hasattr(issue.fields, "customfield_10005"):
        return getattr(issue.fields, "customfield_10005");
    return None

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

    parser.add_argument('--test', required=False, action="store_true", \
            default=False, \
            help='Run test case and then exit')

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
# General nodes
################################################################################
def root_nodes_start(f, key):
    f.write("<map version=\"freeplane 1.6.0\">\n")
    f.write("<node LINK=\"%s\" TEXT=\"%s\" FOLDED=\"false\" COLOR=\"#000000\" LOCALIZED_STYLE_REF=\"AutomaticLayout.level.root\">\n"
        % (g_server + "/projects/" + key, key))

def root_nodes_end(f):
    f.write("</node>\n</map>")

def orphan_node_start(f):
    f.write("<node TEXT=\"Orphans\" POSITION=\"left\" FOLDED=\"false\" COLOR=\"#000000\">\n")

def orphan_node_end(f):
    f.write("</node>\n")

################################################################################
# Test
################################################################################
def test():
    f = open_file("test" + ".mm")
    root_nodes_start(f, "Test")
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
    n202.set_state("In Progress")
    n203 = Node("SWG-203", "My issue 203", "Story")
    n203.set_state("Blocked")
    n204 = Node("SWG-204", "My issue 204", "Story")
    n204.set_state("In Progress")
    n205 = Node("SWG-205", "My issue 205", "Story")

    n14.add_child(n202)
    n14.add_child(n203)
    n14.add_child(n204)
    n14.add_child(n205)
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

    n1.gen_tree()
    n1.to_xml(f)
    root_nodes_end(f)
    f.close()

################################################################################
# Stories
################################################################################
def build_story_node(jira, story_key, d_handled=None, epic_node=None):
    si = jira.issue(story_key)
    if si.fields.status.name in ["Closed", "Resolved"]:
        d_handled[str(si.key)] = [None, si]
        return None

    story = Node(str(si.key), str(si.fields.summary), str(si.fields.issuetype))
    try:
        story.add_assignee(str(si.fields.assignee))
    except:
        story.add_assignee("Unknown")
    story.set_state(str(si.fields.status.name))
    story.set_base_url(g_server)

    if epic_node is not None:
        story.add_parent(epic_node.get_key())
        epic_node.add_child(story)
    else:
        # This cateches when people are not using implements/implemented by, but
        # there is atleast an "Epic" link that we can use.
        parent = get_parent_key(jira, si)
        if parent is not None and parent in d_handled:
            parent_node = d_handled[parent][0]
            if parent_node is not None:
                story.add_parent(parent_node)
                parent_node.add_child(story)
            else:
                vprint("Didn't find any parent")

    print(story)
    d_handled[story.get_key()] = [story, si]
    return story


################################################################################
# Epics
################################################################################
def build_epics_node(jira, epic_key, d_handled=None, initiative_node=None):
    ei = jira.issue(epic_key)

    if ei.fields.status.name in ["Closed", "Resolved"]:
        d_handled[str(ei.key)] = [None, ei]
        return None

    epic = Node(str(ei.key), str(ei.fields.summary), str(ei.fields.issuetype))
    try:
        epic.add_assignee(str(ei.fields.assignee))
    except:
        epic.add_assignee("Unknown")
    epic.set_state(str(ei.fields.status.name))

    try:
        sponsors = ei.fields.customfield_10101
        if sponsors is not None:
            for s in sponsors:
                epic.add_sponsor(str(s.value))
    except AttributeError:
        epic.add_sponsor("No sponsor")


    epic.set_base_url(g_server)

    if initiative_node is not None:
        epic.add_parent(initiative_node.get_key())
        initiative_node.add_child(epic)
    else:
        # This cateches when people are not using implements/implemented by, but
        # there is atleast an "Initiative" link that we can use.
        parent = get_parent_key(jira, ei)
        if parent is not None and parent in d_handled:
            parent_node = d_handled[parent][0]
            if parent_node is not None:
                epic.add_parent(parent_node)
                parent_node.add_child(epic)
            else:
                vprint("Didn't find any parent")

    d_handled[epic.get_key()] = [epic, ei]

    # Deal with stories
    for link in ei.fields.issuelinks:
        if "inwardIssue" in link.raw:
            story_key = str(link.inwardIssue.key)
            build_story_node(jira, story_key, d_handled, epic)

    print(epic)
    return epic

################################################################################
# Initiatives
################################################################################
def build_initiatives_node(jira, issue, d_handled):
    if issue.fields.status.name in ["Closed", "Resolved"]:
        d_handled[str(issue.key)] = [None, issue]
        return None

    initiative = Node(str(issue.key), str(issue.fields.summary), str(issue.fields.issuetype))
    try:
        initiative.add_assignee(str(issue.fields.assignee))
    except:
        initiative.add_assignee("Unknown")

    initiative.set_state(str(issue.fields.status.name))
    sponsors = issue.fields.customfield_10101
    if sponsors is not None:
        for s in sponsors:
            initiative.add_sponsor(str(s.value))
    initiative.set_base_url(g_server)
    print(initiative)

    d_handled[initiative.get_key()] = [initiative, issue] # Initiative

    # Deal with Epics
    for link in issue.fields.issuelinks:
        if "inwardIssue" in link.raw:
            epic_key = str(link.inwardIssue.key)
            build_epics_node(jira, epic_key, d_handled, initiative)

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

    # Now we three list of Jira tickets not touched before, let's go over them
    # staring with Initiatives, then Epics and last Stories. By doing so we
    # should get them nicely layed out in the orphan part of the tree.

    nodes = []
    vprint("Orphan Initiatives ...")
    for i in orphans_initiatives:
        node = build_initiatives_node(jira, i, d_handled)
        nodes.append(node)

    vprint("Orphan Epics ...")
    for i in orphans_epics:
        node = build_epics_node(jira, str(i.key), d_handled)
        nodes.append(node)

    vprint("Orphan Stories ...")
    for i in orphans_stories:
        node = build_story_node(jira, str(i.key), d_handled)
        nodes.append(node)

    return nodes

################################################################################
# Main function
################################################################################
def main(argv):
    global g_args
    global g_yml_config
    global g_config_filename

    # This initiates the global yml configuration instance so it will be
    # accessible everywhere after this call.
    initiate_config(g_config_filename)
    
    key = "SWG"
    parser = get_parser()

    # The parser arguments are accessible everywhere after this call.
    g_args = parser.parse_args()

    if g_args.test:
        test()
        exit()

    jira, username = get_jira_instance(g_args.t)

    if g_args.project:
        key = g_args.project


    # Open and initialize the file
    f = open_file(key + ".mm")
    root_nodes_start(f, key)

    # Temporary dictorionary to keep track the data (issues) that we already
    # have dealt with.
    d_handled = {}

    # Build the main tree with Initiatives beloninging to the project.
    nodes = build_initiatives_tree(jira, key, d_handled)

    # Take care of the orphans, i.e., those who has no connection to any
    # initiative in your project.
    nodes_orpans  = build_orphans_tree(jira, key, d_handled)

    # FIXME: We run through this once more since, when we run it the first time
    # we will catch Epics and Stories who are not linked with
    # "implements/implemented by" but instead uses the so called "Epic" link.
    nodes_orpans  = build_orphans_tree(jira, key, d_handled)

    # Dump the main tree to file
    for n in sorted(nodes):
        n.to_xml(f)

    orphan_node_start(f)
    for n in sorted(nodes_orpans):
        n.to_xml(f)
    orphan_node_end(f)

    # End the file
    root_nodes_end(f)
    f.close()

if __name__ == "__main__":
    main(sys.argv)
