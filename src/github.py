from datetime import datetime, timedelta

from src import requests

GH_BASE_URL = "https://api.github.com"


class Github:
    def __init__(self, github_repo: str, github_token: str):
        self.github_token = github_token
        self.github_repo = github_repo

    def make_headers(self) -> dict:
        return {
            'authorization': f'Bearer {self.github_token}',
            'content-type': 'application/json',
        }

    def get_deletable_branches(self, last_commit_age_days: int, ignore_branches: list) -> list:
        # Default branch might not be protected
        default_branch = self.get_default_branch()

        url = f'{GH_BASE_URL}/repos/{self.github_repo}/branches'
        headers = self.make_headers()

        response = requests.get(url=url, headers=headers, force_debug=True)
        if response.status_code != 200:
            raise RuntimeError(f'Failed to make request to {url}. {response} {response.json()}')

        deletable_branches = []
        branch: dict
        for branch in response.json():
            branch_name = branch.get('name')

            commit_hash = branch.get('commit', {}).get('sha')
            commit_url = branch.get('commit', {}).get('url')

            # Immediately discard protected branches, default branch and ignored branches
            if branch.get('protected') is True or branch_name == default_branch or branch_name in ignore_branches:
                continue

            # Move on if commit is in an open pull request
            if self.has_open_pulls(commit_hash=commit_hash):
                continue

            # Move on if last commit is newer than last_commit_age_days
            if self.is_commit_older_than(commit_url=commit_url, older_than_days=last_commit_age_days):
                continue

            deletable_branches.append(branch_name)

        print(deletable_branches)

        return deletable_branches

    def get_default_branch(self) -> str:
        url = f'{GH_BASE_URL}/repos/{self.github_repo}'
        headers = self.make_headers()

        response = requests.get(url=url, headers=headers, force_debug=True)

        return response.json().get('default_branch')

    def has_open_pulls(self, commit_hash: str) -> bool:
        url = f'{GH_BASE_URL} /repos/{self.github_repo}/commits/{commit_hash}/pulls'
        headers = self.make_headers()
        headers['accept'] = 'application/vnd.github.groot-preview+json'

        response = requests.get(url=url, headers=headers, force_debug=True)
        if response.status_code != 200:
            raise RuntimeError(f'Failed to make request to {url}. {response} {response.json()}')

        pull_request: dict
        for pull_request in response.json():
            if pull_request.get('state') == 'open':
                return True

        return False

    def is_commit_older_than(self, commit_url: str, older_than_days: int):
        response = requests.get(url=commit_url, headers=self.make_headers(), force_debug=True)
        if response.status_code != 200:
            raise RuntimeError(f'Failed to make request to {commit_url}. {response} {response.json()}')

        commit: dict = response.json().get('commit', {})
        committer: dict = commit.get('committer', {})
        author: dict = commit.get('author', {})

        # Get date of the committer (instead of the author) as the last commit could be old but just applied
        # for instance coming from a merge where the committer is bringing in commits from other authors
        # Fall back to author's commit date if none found for whatever bizarre reason
        commit_date_raw = committer.get('date', author.get('date'))
        if commit_date_raw is None:
            print(f"Warning: could not determine commit date for {commit_url}. Assuming it's not old enough to delete")
            return False

        # Dates are formatted like so: '2021-02-04T10:52:40Z'
        commit_date = datetime.strptime(commit_date_raw, "%Y-%m-%dT%H:%M:%SZ")

        return datetime.now() > (commit_date + timedelta(days=older_than_days))
