#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import ArgumentParser

import os
import re
import sys
import unicodedata
import yaml

# Local files
import cfg
import jiralogin
from helper import vprint, eprint

################################################################################
# Argument parser
################################################################################
def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to generate Freeplane mindmap files')

    parser.add_argument('-i', required=False, action="store_true", \
            default=False, \
            help='Show Initiatives only')

    parser.add_argument('-p', '--project', required=False, action="store", \
            default="SWG", \
            help='Project type (SWG, VIRT, KWG etc)')

    parser.add_argument('-s', required=False, action="store_true", \
            default=False, \
            help='Show stories also')

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
# Estimation
################################################################################
def get_fte_next_cycle(issue):
    if hasattr(issue.fields, "customfield_11801"):
        return issue.fields.customfield_11801
    else:
        return 0

def get_fte_remaining(issue):
    if hasattr(issue.fields, "customfield_12000"):
        return issue.fields.customfield_12000
    else:
        return 0

def issue_type(link):
    return link.outwardIssue.fields.issuetype.name

def issue_link_type(link):
    return link.type.name

def issue_key(link):
    return link.outwardIssue.key

def issue_remaining_estimate(jira, issue):
    if issue.fields.timetracking.raw is not None:
        est = issue.fields.timetracking.raw['remainingEstimateSeconds']
        return est
    else:
        eprint("Warning: Found no estimate in {}, returning '0'!".format(issue.key))
        return 0

def gather_epics(jira, key):
    jql = "project={} AND issuetype in (Epic) AND status not in (Resolved, Closed)".format(key)
    #jql = "project={} AND key in (SWG-260, SWG-262, SWG-323) AND issuetype in (Epic) AND status not in (Resolved, Closed)".format(key)
    #jql = "project={} AND key in (SWG-360, SWG-361) AND issuetype in (Epic) AND status not in (Resolved, Closed)".format(key)
    jql = "project={} AND key in (SWG-320) AND issuetype in (Epic) AND status not in (Resolved, Closed)".format(key)
    return jira.search_issues(jql)

def find_epic_parent(jira, epic):
    initiative = {}
    for l in epic.fields.issuelinks:
        link = jira.issue_link(l) 
        if issue_type(link) == "Initiative" and issue_link_type(link) == "Implements":
            print("E/{}: I/{} ({})".format(epic, issue_key(link), issue_type(link)))
            if len(initiative) == 0:
                initiative[issue_key(link)] = epic
            else:
                eprint("Error: Epic {} has more than one parent!".format(epic_key.key))
    vprint("Initiative/Epic: {}".format(initiative))
    return initiative


def find_epics_parents(jira, epics):
    """ Returns a dictionary where Initiative is key and value is a list of Epic Jira objects """
    initiatives = {}
    for e in epics:
        tmp = find_epic_parent(jira, e)
        for i, e in tmp.items():
            if i in initiatives:
                initiatives[i].append(e)
            else:
                initiatives[i] = [e]

    vprint(initiatives)
    return initiatives

def update_initiative_estimates(jira, initiatives):
    for i, e in initiatives.items():
        fte_next_cycle = 0
        fte_remaining = 0
        for epic in e:
            # Need to do this to get all information about an issue
            epic = jira.issue(epic.key)
            est = issue_remaining_estimate(jira, epic)
            vprint("Epic: {}, remainingEstimate: {}".format(epic, est))
            # Add up everything
            fte_remaining += est
            # Add up things for the next cycle
            if hasattr(epic.fields, "labels") and "NEXT-CYCLE" in epic.fields.labels:
                fte_next_cycle += est
        initiative = jira.issue(i)
        print("Initiative {} ({}/{}): fte_next: {} fte_remain: {}".format(i, get_fte_next_cycle(initiative), get_fte_remaining(initiative), fte_next_cycle, fte_remaining))

################################################################################
# Config files
################################################################################
def get_config_file():
    """ Returns the location for the config file (including the path). """
    for d in cfg.config_locations:
        for f in [cfg.config_filename, cfg.config_legacy_filename]:
            checked_file = d + "/" + f
            if os.path.isfile(checked_file):
                return d + "/" + f

def initiate_config():
    """ Reads the config file (yaml format) and returns the sets the global
    instance.
    """
    cfg.config_file = get_config_file()
    if not os.path.isfile(cfg.config_file):
        create_default_config()

    vprint("Using config file: %s" % cfg.config_file)
    with open(cfg.config_file, 'r') as yml:
        cfg.yml_config = yaml.load(yml, Loader=yaml.FullLoader)

################################################################################
# Main function
################################################################################
def main(argv):
    parser = get_parser()

    # The parser arguments (cfg.args) are accessible everywhere after this call.
    cfg.args = parser.parse_args()

    # This initiates the global yml configuration instance so it will be
    # accessible everywhere after this call.
    initiate_config()

    key = "SWG"

    if cfg.args.test:
        test()
        exit()

    jira, username = jiralogin.get_jira_instance(cfg.args.t)

    if cfg.args.project:
        key = cfg.args.project

    epics = gather_epics(jira, key)

    for e in epics:
        print(e)

    initiatives = find_epics_parents(jira, epics)

    update_initiative_estimates(jira, initiatives)

    exit()


    # Open and initialize the file
    f = open_file(key + ".mm")

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
