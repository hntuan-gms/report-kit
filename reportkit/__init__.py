"""reportkit - black-box test kit for report / search / statistics screens.

The core never names a project. Everything project-specific (systems, login, DB, code map,
standard rules, workbook template, function list) lives in a *profile*: a folder with
project.yaml, found by walking up from the current directory to `.report-kit/project.yaml`
or given with --profile / RK_PROFILE.
"""
__version__ = "0.1.0"
