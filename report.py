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

JQL = "project = {} AND issuetype in (Epic, Initiative, Story) AND status in (Resolved, Closed) AND resolved >= -5w AND resolved <= \"0\" ORDER BY cf[10005] DESC"

IGNORE_LIST = []
DRY_RUN = False
NEXT_CYCLE_UPDATE = False

###############################################################################
# Argument parser
###############################################################################


def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to create a monthly + '
                            'health check report')

    parser.add_argument('-c', '--show-comments', required=False,
                        action="store_true", default=False,
                        help='Show comments in report')

    parser.add_argument('-p', '--project', required=False, action="store",
                        default="SWG",
                        help='Project type (SWG, PMWG, KWG etc)')

    parser.add_argument('-t', required=False, action="store_true",
                        default=False,
                        help='Use the test server')

    parser.add_argument('-v', required=False, action="store_true",
                        default=False,
                        help='Output some verbose debugging info')

    return parser

###############################################################################
# Report
###############################################################################


def issue_type(link):
    return link.outwardIssue.fields.issuetype.name


def issue_link_type(link):
    return link.type.name


def issue_key(link):
    return link.outwardIssue.key


def find_updated_epics(jira, key):
    global JQL
    print("Running query for Epics ...\n")
    return jira.search_issues(JQL.format(key))


def find_epic_parent(jira, epic):
    initiative = {}
    for l in epic.fields.issuelinks:
        link = jira.issue_link(l)
        if issue_type(link) == "Initiative" and \
                issue_link_type(link) == "Implements":
            print("  E/{} ... found parent I/{}".format(epic, issue_key(link)))
            if len(initiative) == 0:
                initiative[issue_key(link)] = epic
            else:
                eprint("  Error: Epic {} has more than one parent!".
                       format(epic_key.key))
    vprint("  Initiative/Epic: {}".format(initiative))
    return initiative


def find_epics_parents(jira, epics):
    """ Returns a dictionary where Initiative is key and value is a list of
    Epic Jira objects """
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


def update_initiative(jira, initiative, fte_next, fte_remain):
    global IGNORE_LIST
    if initiative.key in IGNORE_LIST:
        print("  NOT updating {} (found in the ignore list)".
              format(initiative.key))
        return

    ftes = "Next and Remaining" if NEXT_CYCLE_UPDATE else "Remaining only"
    print("  Updating FTE's ({}) in {}".format(ftes, initiative.key))
    if NEXT_CYCLE_UPDATE:
        update_fte_next_cycle(initiative, fte_next)
    update_fte_remaining(initiative, fte_remain)


def get_lp_name(issue):
    if hasattr(issue.fields, "customfield_10043"):
        lp_obj = getattr(issue.fields, "customfield_10043");
        return str(lp_obj[0])
    return "N/A"


def create_report(jira, initiatives, show_comments):
    full_report = ""
    for i, e in initiatives.items():
        initiative = jira.issue(i)
        print("\n{}\nLead Project: {}".
              format("="*80, get_lp_name(initiative)))
        print("\n{} ({})".
              format(initiative.fields.summary, initiative.key))
        print("* No. tickets closed: {}".format(len(e)))
        for epic in e:
            # Need to do this to get all information about an issue
            epic = jira.issue(epic.key)
            print("* {}: {}".
                  format(epic.key, epic.fields.summary))
            if (show_comments):
                c = jira.comments(epic.key)
                if len(c) > 2:
                    print("{}\n{}\n\n{}\n{}\n".
                          format("---", c[-2].body, c[-1].body, "---"))


###############################################################################
# Config files
###############################################################################


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


###############################################################################
# Main function
###############################################################################


def main(argv):
    global JQL
    parser = get_parser()

    # The parser arguments (cfg.args) are accessible everywhere after this
    # call.
    cfg.args = parser.parse_args()

    # This initiates the global yml configuration instance so it will be
    # accessible everywhere after this call.
    initiate_config()

    key = "SWG"

    jira, username = jiralogin.get_jira_instance(cfg.args.t)

    if cfg.args.project:
        key = cfg.args.project

    show_comments = False
    if cfg.args.show_comments:
        show_comments = cfg.args.show_comments

    epics = find_updated_epics(jira, key)

    print("Processing all Epics found by JQL query:\n  '{}'".
          format(JQL.format(key)))
    initiatives = find_epics_parents(jira, epics)

    create_report(jira, initiatives, show_comments)

    jira.close()
    print("Done!")


if __name__ == "__main__":
    main(sys.argv)
