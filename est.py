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

JQL = "project={} AND issuetype in (Epic) AND status not in (Resolved, Closed)"

# Left as string for development / test purpose
# JQL = "project={} AND key in (SWG-260, SWG-262, SWG-323) AND issuetype in (Epic) AND status not in (Resolved, Closed)"
# JQL = "project={} AND key in (SWG-360, SWG-361) AND issuetype in (Epic) AND status not in (Resolved, Closed)"
# JQL = "project={} AND key in (SWG-320) AND issuetype in (Epic) AND status not in (Resolved, Closed)"

IGNORE_LIST = []

###############################################################################
# Argument parser
###############################################################################


def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to automatically + '
                            'update FTE fields in Initiatives')

    parser.add_argument('-c', required=False, action="store_true",
                        default=False,
                        help='Create ignore list (ignore_estimate.txt) fully \
                              populated')

    parser.add_argument('-i', required=False, action="store_true",
                        default=False,
                        help='Use ignore list (ignore_estimate.txt)')

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
# Estimation
###############################################################################


def seconds_per_day():
    """ 60 seconds * 60 minutes * 8 hours """
    return 60*60*8


def seconds_per_week():
    return seconds_per_day() * 5.0


def seconds_per_month():
    return seconds_per_week() * 4.0


def to_months(seconds):
    return seconds / seconds_per_month()


def to_seconds(months):
    return months * seconds_per_month()


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


def update_fte_next_cycle(issue, fte_next):
    if hasattr(issue.fields, "customfield_11801"):
        issue.update(fields={'customfield_11801': fte_next}, notify=False)
    else:
        print("  Warning: [{}: {}] doesn't have a FTE next cycle field, no " +
              "update done!".format(issue.key, issue.fields.summary))


def update_fte_remaining(issue, fte_remain):
    if hasattr(issue.fields, "customfield_12000"):
        issue.update(fields={'customfield_12000': fte_remain}, notify=False)
    else:
        print("  Warning: [{}: {}] doesn't have a FTE remaining field, no " +
              "update done!".format(issue.key, issue.fields.summary))


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
        print("  Warning: Found no estimate in Epic {} (returning 0 as estimate)!".format(issue.key))
        return 0


def gather_epics(jira, key):
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

    print("  Updating FTE's in {}".format(initiative.key))
    update_fte_next_cycle(initiative, fte_next)
    update_fte_remaining(initiative, fte_remain)


def update_initiative_estimates(jira, initiatives):
    for i, e in initiatives.items():
        initiative = jira.issue(i)
        print("\nWorking with Initiative {}: {}".
              format(initiative.key, initiative.fields.summary))
        fte_next_cycle = 0
        fte_remaining = 0
        for epic in e:
            # Need to do this to get all information about an issue
            epic = jira.issue(epic.key)
            est = issue_remaining_estimate(jira, epic)
            vprint("  Epic: {}, remainingEstimate: {}".format(epic, est))
            # Add up everything
            fte_remaining += est
            # Add up things for the next cycle
            if hasattr(epic.fields, "labels") and \
                    "NEXT-CYCLE" in epic.fields.labels:
                fte_next_cycle += est
        fte_next_nbr_months = to_months(fte_next_cycle)
        fte_remain_nbr_months = to_months(fte_remaining)
        print("  Initiative {} Current(N/R): {}/{}: True(N/R): {}/{}".format(
            i,
            get_fte_next_cycle(initiative), get_fte_remaining(initiative),
            fte_next_nbr_months, fte_remain_nbr_months))
        update_initiative(jira, initiative, fte_next_nbr_months,
                          fte_remain_nbr_months)


def create_ignore_list(jira, key):
    jql = "project={} AND issuetype in (Initiative) AND status not in (Resolved, Closed)".format(key)
    initiatives = jira.search_issues(jql)

    with open("ignore_estimate.txt", 'w') as f:
        for i in initiatives:
            f.write("{} {}\n".format(i.key, i.fields.summary))


def load_ignore_list():
    global IGNORE_LIST
    with open("ignore_estimate.txt", 'r') as f:
        initiatives = f.readlines()
        print("Adding following to the ignore list (no estimate updates for " +
              "these):")
        for i in initiatives:
            issue = i.split()[0]
            print("  * {}".format(i.strip('\n')))
            IGNORE_LIST.append(issue)


def should_update(question):
    """ A yes or no dialogue. """
    while True:
        answer = input(question + " [y/n] ").lower().strip()
        if answer in set(['y', 'n']):
            return answer
        else:
            print("Incorrect input: %s" % answer)

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
    global IGNORE_LIST
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

    if cfg.args.c:
        create_ignore_list(jira, key)
        exit()

    if cfg.args.i:
        load_ignore_list()
        question = "Ignore list correct? Still continue?"
        if should_update(question) == "n":
            jira.close()
            sys.exit()
    else:
        question = "No ignore list loaded, still continue? All Initiatives " \
                   "will be updated!"
        if should_update(question) == "n":
            jira.close()
            sys.exit()

    epics = gather_epics(jira, key)

    print("Processing all Epics found by JQL query:\n  '{}'".
          format(JQL.format(key)))
    initiatives = find_epics_parents(jira, epics)

    update_initiative_estimates(jira, initiatives)

    jira.close()
    print("Done!")


if __name__ == "__main__":
    main(sys.argv)
