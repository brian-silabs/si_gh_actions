# si_gh_actions

## Documentation

### Steps

Locally :

* `git init`
* `git remote add origin "url"`
* `git pull origin main`
* `git submodule add [https://github.com/brian-silabs/si_gh_actions.git](https://github.com/brian-silabs/si_gh_actions.git)`
* `python3 si_gh_actions/boardlessify.py`

On Github :

* Create an access token with below permissions :
* Create a repository Secret named ACCESS_TOKEN
* Paste content of token there
* Authorize Read/Write permissions for actions runner in Settings->Actions->General->Workflow permissions

Once done :

* Publish both branches
* Set dev branch as default (you might need to re-run 1st job)

## Issues

* .gitignore not applied on new dev branch
  * But confi/zcl or bt must be kept
* Currently building only on BRD4186C
    Maybe using a matrix config based on a json file
