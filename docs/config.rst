.. _config_file:

###########
Config file
###########

Location
========
If you haven't used Jipdate before, then the script will create a
``.jipdate.yml`` config automatically. It will store it at one of the following
locations.

.. code-block:: none

    $HOME/.config/jipdate/.jipdate.yml
    $HOME/.jipdate.yml
    $HOME/.../<jipdate-script-dir>/.jipdate.yml

You can move it to any of the three folders if you have any preference.


.. _example_config:

Example config
==============
Jipdate config files are written in `YAML format`_ and a typical config file
looks like this:

.. code-block:: yaml

    # Config file for jipdate
    # For use in future (backwards compatibility)
    version: 1

    # Extra comments added to each Jira issue (multiline is OK)
    comments:
        - "# No updates since last week."

    # Header of the file (multiline is OK). It will be followed by
    header:
        - |
          Hi,

          This is the status update from me for the
          last week.

          Cheers!

    # Set this to 'True' if you want to get the issue header merged with the issue
    # number.
    use_combined_issue_header: False

    # Default separator in the issue header, change to the separator of your own
    # preference.
    separator: ' | '
    text-editor: True
    username: john.doe@linaro.org

You will need to re-run the script after making a changes to the config file.


Config options
==============

auth-token
----------
If you prefer or must use a token based login, then you should set the
``auth-token`` variable in config-file. You can retrieve the token by doing the
following:

* Go to https://id.atlassian.com/manage-profile/profile-and-visibility
* Click on "Security" (left hand side)
* Click on "Create and manage API tokens"
* Click on "Create API token"


comments
--------
This can be used to put a default line(s) showing up at each Jira ticket when
doing a query. I.e., this is what is shown at line **5** and **11** in the
example below.


.. code-block:: ini
    :linenos:
    :emphasize-lines: 5, 11

    [SWG-355]
    # Header: Centralize and update OP-TEE documentation
    # Type: Epic
    # Status: In Progress
    # No updates since last week.

    [SWG-338]
    # Header: OP-TEE issues at GitHub
    # Type: Epic
    # Status: To Do
    # No updates since last week.


header
------
This where you can put general information that you want to provide with a
status update in email format for example. This will always be put on top in the
output from Jira, i.e., before any individual ticket sections. So with the text
in the :ref:`example_config` above, jipdate will produce this (see line 3-7).

.. code-block:: ini
    :linenos:
    :emphasize-lines: 3-7

    Subject: [Weekly] Week ending 2019-01-22

    Hi,

    This is the status update from me for the last week.

    Cheers!


    John Doe


    [SWG-355]
    # Header: Centralize and update OP-TEE documentation
    # Type: Epic
    # Status: In Progress
    # No updates since last week.
    ...

The above is the short default example. You could of course be more creative
here and instead list a couple of different sections that are relevant to the
status report for your team. For example something like this might be more
useful.

.. code-block:: yaml

    header:
        - |
          Hi,

          This is the status update from me for the last week.

          * Ongoing:
           ** Jira
              For individual tickets I'm working with, please have a look at the
              Jira sections below.

           ** None Jira:

          * Travels
            No planned travels

          * Vacations / time-off:
            No planned time off in the coming weeks.

          // Regards


Which would generate this:

.. code-block:: ini
    :linenos:
    :emphasize-lines: 3-7

    Subject: [Weekly] Week ending 2019-01-22
    
    Hi,
    
    This is the status update from me for the last week.
    
    * Ongoing:
      ** Jira
           For individual tickets I'm working with, please have a look at the
               Jira sections below.
    
      ** None Jira:
    
    * Travels
      No planned travels
    
    * Vacations / time-off:
      No planned time off in the coming weeks.
    
    // Regards
    Joakim Bech
    
    [SWG-355]
    ...


use_combined_issue_header
-------------------------
This will decide if ``[XYZ-123]`` and the name of the ticket name should be
merged into a single line or not. I.e.

``use_combined_issue_header: False`` gives:

.. code-block:: ini
    :linenos:
    :emphasize-lines: 1

    [SWG-355]
    # Header: Centralize and update OP-TEE documentation
    # Type: Epic
    # Status: In Progress
    # No updates since last week.
    ...

``use_combined_issue_header: True`` gives:

.. code-block:: ini
    :linenos:
    :emphasize-lines: 1

    [SWG-355 | Centralize and update OP-TEE documentation]
    # Type: Epic
    # Status: In Progress
    # No updates since last week.

separator
---------
This gives the Jipdate user the ability to use another separate than the default
``|``. This is only useful if ``use_combined_issue_header: True``. For example
if you change it to:

.. code-block:: yaml

    separator: ': '

Then Jipdate will output Jira sections like this:

.. code-block:: ini

    [SWG-355: Centralize and update OP-TEE documentation]
    # Type: Epic
    # Status: In Progress
    # No updates since last week.


text-editor
-----------
This is a simple ``True`` and ``False`` deciding whether you would like to spawn
your preferred text editor with the results after a successfull Jira query. To
make use of this, please set the ``EDITOR`` enviroment variable before invoking
Jipdate, e.g., something like:

.. code-block:: bash

    export EDITOR=vim


.. _username:

username
--------
If this exists in the config, then jipdate will **not** ask for the username
when running the script (see the :ref:`example_config` for the syntax).


.. _YAML format: https://yaml.org/spec/1.2/spec.html
