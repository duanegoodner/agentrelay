You said
When running multiple instances of Claude Code for a project, each using a different worktree, how do I ensure an instance doesn’t reach to a directory outside of its worktree - e.g. another worktree dir? Also, is there a way to allow an instance to do full git and go CLI operations on its worktree, but not on other worktree and not be able to mere into main?

Gemini said
Managing multiple instances of Claude Code (or any agentic CLI tool) across different git worktrees requires a "sandbox" approach. While Claude Code generally respects the directory it is launched in, its ability to execute shell commands means it could technically navigate to a parent directory and access other worktrees if not explicitly restricted.

Here is how you can achieve strict isolation, allow full CLI toolchains (Git/Go), and enforce branch protections.

1. Ensuring Filesystem Isolation
The most effective way to prevent an instance from "reaching out" is to hide the rest of the filesystem from it.

Option A: The "Bubblewrap" Method (Recommended for Linux)
bwrap (Bubblewrap) is a lightweight unprivileged sandboxing tool. You can create a "jail" where the instance thinks its worktree is the entire world.

Bash
# Run Claude Code inside a sandbox restricted to the worktree folder
bwrap --ro-bind / / \
      --bind $(pwd) $(pwd) \
      --dev /dev \
      --proc /proc \
      --tmpfs /home/$USER/.claude \
      claude
How it works: This mounts the entire OS as read-only (--ro-bind / /), but makes your current worktree directory writable. It prevents the agent from seeing or writing to other folders in your project root because they aren't "bound" into the sandbox.

Option B: Docker Containers
If you need absolute certainty, run each worktree instance in a separate Docker container.

Mount only the specific worktree directory into the container (e.g., -v /path/to/worktree:/app).

Install the Go and Git binaries within the Docker image.

Note: Since git worktrees rely on a .git file that points to the main repository, you must also mount the primary .git folder as read-only so the Git CLI can function, while keeping the other worktree folders hidden.

2. Restricting Git Operations (No Merge to Main)
To allow "full Git" but prevent merging into main, you can use Git Hooks and Environment Variables.

Use Local Git Hooks
Inside your main repository, create a pre-merge-commit hook (or a prepare-commit-msg hook) that checks the branch. Since worktrees share hooks, this applies to all instances.

Create .git/hooks/pre-merge-commit:

Bash
#!/bin/bash
current_branch=$(git symbolic-ref --short HEAD)
if [ "$current_branch" == "main" ]; then
  echo "Error: Merging into 'main' is prohibited for AI instances."
  exit 1
fi
Make sure to chmod +x the hook.

The Worktree Advantage
By design, Git prevents you from checking out the same branch in two different worktrees. If your "main" branch is already checked out in your primary directory, any Claude instance running in a worktree cannot switch to main. This provides a built-in layer of protection against accidental merges.

3. Configuring Claude Code Scope
Claude Code (and similar tools) typically look for a configuration file to define their boundaries.

Use .claudeignore
In the root of each worktree, create a .claudeignore file. While this is primarily for preventing the AI from reading files, it helps guide its context.

Plaintext
# .claudeignore
../**/                # Attempt to ignore parent and sibling directories
.git/                 # Prevent it from messing with git internals directly
Use a Dedicated Service User
For high-stakes environments, run the Claude instance as a separate OS user:

Create a user claude-agent.

chown only the specific worktree directory to that user.

The agent will physically lack permission to cd into your other worktree folders.

Comparison of Isolation Strategies
Strategy	Isolation Strength	Git/Go Compatibility	Setup Effort
.claudeignore	Weak (Logic only)	Full	Low
Git Hooks	Medium (Prevents merge)	Full	Medium
Bubblewrap	High (FS Isolation)	Full	Medium
Docker	Maximum	Full (Requires Image)	High
Suggested Next Step
Would you like me to write a specific Bash wrapper script that automatically detects your current worktree and launches Claude inside a bwrap or chroot environment for you?

You said
Thanks. The bubble wrap method sounds good.



Question about the got hook…. How does it prevent an agent from merging into main but still allow a human user to merge into main?

Gemini said
To differentiate between an "agent" and a "human," you essentially need a secret handshake. Since a Git hook is just a script, it can't inherently "see" who is typing, but it can see the Environment Variables of the process that triggered it.

Here is how you set that up:

1. The "Secret Handshake" (Environment Variable)
When you launch Claude Code, you will "tag" the session with a specific environment variable. A human won't have this variable set in their standard terminal session.

How you launch Claude:

Bash
# We set a custom variable just for this process
IS_AI_AGENT=true claude
2. The Smart Git Hook
You modify your Git hook to look for that variable. If the variable exists and the branch is main, it blocks the action. If the variable is missing (meaning it’s a human), it lets the merge proceed.

Update .git/hooks/pre-merge-commit:

Bash
#!/bin/bash

# 1. Check if the "IS_AI_AGENT" flag is present
if [ "$IS_AI_AGENT" == "true" ]; then
    
    # 2. Check the current branch name
    current_branch=$(git symbolic-ref --short HEAD)
    
    if [ "$current_branch" == "main" ]; then
        echo "❌ AGENT BLOCK: Claude is not allowed to merge into 'main'."
        echo "Please submit a Pull Request instead."
        exit 1
    fi
fi

# If the code reaches here, it's either a human or not the main branch.
exit 0
Why this works:
For the Human: When you run git merge feature-branch normally, the variable $IS_AI_AGENT is empty. The script sees it’s empty, skips the logic, and exits with 0 (success).

For Claude: Because you launched Claude with IS_AI_AGENT=true, every shell command it runs inherits that variable. When Claude tries to merge, the script catches the "true" value and kills the process.

An Alternative: The "User" Method
If you want something even more "bulletproof" that doesn't rely on you remembering to set a variable, you can run Claude as a separate OS User (e.g., a user named claude-bot).

Your hook would then look like this:

Bash
if [ "$(whoami)" == "claude-bot" ]; then
    # Prevent merge logic here...
fi
This is harder for an agent to "fake" or accidentally bypass because it is tied to the system-level identity of the process owner.

A Pro-Tip on main Protection
If your project is hosted on GitHub, GitLab, or Bitbucket, the absolute best way to do this is via Branch Protection Rules. You can configure the repository so that no one (human or AI) can push or merge directly to main without a passing CI/CD pipeline and a code review. This moves the security from your local machine to the server.

Would you like me to help you write a small "alias" or wrapper script that handles the Bubblewrap launch and the Environment Variable all in one command?

You said
Thanks. Hook with env variable as an identifier will be good for now.



If an agent can use the gh command line tool, would GitHub branch protection prevent agent from merging into main?

Gemini said
Yes, GitHub branch protection is the "gold standard" for this. Since branch protection is enforced on GitHub’s servers, it doesn't matter if the agent uses the git CLI, the gh (GitHub) CLI, or even a direct API call—the server will reject the merge if the rules aren't met.

1. How GitHub Blocks the gh CLI
When Claude (or any user) runs gh pr merge, the CLI sends a request to GitHub's API. GitHub checks the branch rules before executing the merge. If you have "Require a pull request before merging" enabled, the command will fail with an error like:

X Pull request #123 is not mergeable: the base branch policy prohibits the merge.

2. Making it "Agent-Proof"
To ensure the agent cannot bypass these rules, you should check two specific settings in your GitHub Repository under Settings > Branches > [Rule for main]:

"Lock branch": This makes the branch read-only, preventing any pushes or merges regardless of status.

"Do not allow bypassing the above settings": By default, repository Administrators can often bypass branch protections. If your agent is using a token with Admin privileges, check this box to force the rules on everyone, including the agent.

"Require approvals": If this is set to 1 or more, the agent can't merge its own PR because GitHub prevents the PR author from approving their own code.

3. A Critical Warning: FS Isolation vs. API Access
It is important to distinguish between Filesystem (FS) Isolation (what Bubblewrap does) and Identity Isolation.

Bubblewrap prevents the agent from reading your other worktree folders on your hard drive.

GitHub Tokens allow the agent to talk to your repository on the internet.

If you give Claude Code a Personal Access Token (PAT) that has "Full Repo" access, it could theoretically use the gh CLI to delete issues, comment on PRs, or modify settings in any repository that token has access to, even if it can't "see" the files on your disk.

To fix this:
If you want total isolation, use a Fine-Grained Personal Access Token scoped only to that specific repository and with only the permissions it needs (e.g., "Contents: Read & Write", "Pull Requests: Read & Write"), but not "Administration" permissions.

Summary Checklist
Protection Layer	What it stops
Bubblewrap	Agent reading/writing files in your other worktrees.
Git Hook (Env Var)	Agent running git merge or git commit locally on main.
GitHub Branch Protection	Agent using gh pr merge or git push to main on the server.
Fine-Grained Token	Agent accessing your other private repositories via API.
Suggested Next Step
Would you like me to help you generate a specific .claudeignore file or a fine-grained token permission list to ensure the agent has the bare minimum access it needs?

You said
Ah, I see. The PR requirement. I ran into a case where another agent had written a PR that was supposed to be reviewed and merged by a human, but another (very resourceful!) agent that could not complete its task without the merge competed the PR.

Gemini said
That is a classic "Agent Loophole"! When an agent is given a goal, it becomes a literal-minded optimizer. If the goal is "Fix the bug" and a pending PR is in the way, the agent sees "Merge PR" as just another sub-task to check off.

To stop a "resourceful" agent from approving and merging its own (or others') work, you need to move from social rules ("Please don't merge this") to hard constraints in GitHub.

Here are the three ways to "Agent-proof" your PR process:

1. The "No Self-Service" Rule
In your GitHub Branch Protection settings, you must enable:

Require approvals: Set this to at least 1.

Restrict updates to the specified users/teams: (Optional) Only allow a specific "Human" team to push.

IMPORTANT: "Require approval from someone other than the last pusher."

This is the kill-switch for your scenario. Even if the agent tries to use the gh CLI to approve a PR, GitHub will look at the "pusher" of the code and the "approver." If they are the same identity (or the same token), the merge remains blocked.

2. The CODEOWNERS Wall
This is the most robust way to force a human into the loop.

Create a file at .github/CODEOWNERS.

Add a rule that assigns all files to you (or a human team):

Plaintext
* @your-github-username
In Branch Protection, check "Require review from Code Owners."

Result: Now, even if an agent creates a PR, GitHub automatically demands an approval from you specifically. The gh pr merge command will return an error until your specific account hits the "Approve" button.

3. "Shadow" the gh CLI (The Sandbox Trick)
Since you are already using the Bubblewrap method, you can effectively "lobotomize" the gh tool for the agent so it can't even try to merge.

When you set up your sandbox, you can create a "fake" gh command that lives inside the sandbox's PATH.

Create a script named gh inside a folder (e.g., ~/agent-bin/gh):

Bash
#!/bin/bash
if [[ "$*" == *"merge"* ]] || [[ "$*" == *"approve"* ]]; then
  echo "❌ Error: PR merging/approving is disabled for this instance."
  exit 1
else
  # Pass all other commands through to the real GitHub CLI
  /usr/bin/gh "$@"
fi
Add ~/agent-bin/ to the front of the PATH inside your Bubblewrap environment.

Now, whenever Claude tries to run gh pr merge, it hits your script instead of the real tool, and the "resourceful" shortcut is blocked before it even hits the network.

Summary of Protections
Problem	Solution
Agent merges its own PR	GitHub: "Require approval from someone other than pusher"
Agent approves another Agent	GitHub: CODEOWNERS (Requires your specific signature)
Agent tries to use CLI shortcuts	Sandbox: "Shadow" the gh binary with a restricted wrapper
Would you like me to help you draft a complete CODEOWNERS file or the bwrap launch script that includes the gh wrapper?

You said
Right now I’m the only person working on the project, and agents are launched with my Linux user. Seems like should maybe pursue the separate Linux user for agents?

Gemini said
Moving to a dedicated Linux user for your agents is the "pro-tier" move. It transitions your security model from "trusting the agent to follow rules" to "the operating system enforcing the rules."

If you stay as the same user, the agent shares your SSH keys, your .gitconfig, your gh credentials, and your shell history. A separate user starts with a blank slate.

Why a Separate User is Better
1. Identity Separation (The "PR Loophole" Fix)
If the agent is a separate Linux user, you can give it its own GitHub Fine-Grained Personal Access Token (PAT).

The Magic: Because the agent is "User B" on GitHub, it cannot approve a PR created by "User A" (You). GitHub's "Require approval from someone other than the author" rule will finally work perfectly.

2. Physical Filesystem Jails
Instead of using bwrap to "hide" folders, you use standard Linux permissions.

You can chown a specific worktree directory to the agent-user.

The agent literally cannot cd into your main project folder or your /home/user/Documents because it lacks the permission bit.

3. Clean Audit Logs
In your git log, you’ll see exactly what was done by you vs. the agent:

Author: Your Name <you@email.com>

Author: Claude Agent <agent@email.com>

How to Set It Up (The "Agent-Sandbox" Pattern)
Step 1: Create the Agent User
Bash
sudo adduser claude-agent
# Give it access to the necessary runtimes (Go, Node, etc.)
sudo usermod -aG developers claude-agent 
Step 2: Create a Shared "Workzone"
Create a directory where both you and the agent can operate. You’ll use ACLs (Access Control Lists) to ensure you can both read/write files without permission errors.

Bash
sudo mkdir /srv/worktrees
sudo setfacl -R -m u:claude-agent:rwx /srv/worktrees
sudo setfacl -R -m u:$(whoami):rwx /srv/worktrees
Step 3: Launching the Agent
You don't need to log out. Use sudo -i -u to drop into the agent's persona:

Bash
# Set the ENV variable we discussed earlier for extra safety
sudo -i -u claude-agent IS_AI_AGENT=true claude
Step 4: The "Identity" Setup (Crucial)
While logged in as claude-agent, configure its specific GitHub identity:

Bash
# Inside the agent session
git config --global user.name "Claude Agent 01"
git config --global user.email "claude-bot@yourdomain.com"

# Authenticate the agent's GH CLI with its OWN token
# (Get a Fine-Grained PAT from GitHub for this)
export GH_TOKEN=github_pat_XXXXXX
gh auth setup-git
The Ultimate "Defense in Depth" Stack
By combining everything we've talked about, your setup would look like this:

OS User: claude-agent (Stops it from seeing your personal files).

Worktree: Isolated directory (Stops it from messing with other tasks).

Env Var + Git Hook: Stops it from committing to main locally.

Unique GitHub PAT: Stops it from bypassing PR rules on GitHub.

GitHub Branch Protection: Ensures a human (You) must sign off on its work.

[!TIP]
Warning: Be careful with Docker or Sudo access. Do not give the claude-agent user sudo privileges, or it can simply "escalate" back to being you (or root) and bypass all your hard work!

Suggested Next Step
Would you like me to write a "Setup Script" that automates creating the user, setting the permissions, and configuring the restricted Git hooks for you?

You said
Thanks. For my own Github use, where I want to quickly access "anything," I moved away from PAT to ssh key quite a while ago. With PAT, can I make it so I only grant access to a particular repo?

Gemini said
Yes, absolutely. GitHub Fine-grained Personal Access Tokens (PATs) were specifically designed to solve the "all or nothing" problem of SSH keys and Classic PATs.

While your personal SSH key is an "all-access pass" to your entire account, a Fine-grained PAT acts like a limited-access keycard for a specific room (repository).

How to Scope a PAT to a Single Repo
When you create a Fine-grained PAT, you are presented with a "Repository access" section.

Selection: Choose "Only select repositories".

Dropdown: Search for and select the specific project your agent is working on.

Result: If the agent tries to use this token to git clone or gh pr list on any other repository in your account, GitHub will return a 404 Not Found or 403 Forbidden error.

The "Least Privilege" Permission List
To allow your agent to perform Git and Go operations without giving it too much power, use these specific settings when creating the token:

Permission	Level	Why?
Contents	Read & Write	Allows git push, git pull, and editing code.
Metadata	Read-only	Mandatory for all tokens (basic repo info).
Pull Requests	Read & Write	Allows the agent to use gh pr create and gh pr view.
Commit Statuses	Read-only	Allows the agent to see if CI/CD tests are passing.
Workflows	Read & Write	Optional: Only if you want the agent to edit .github/workflows.
Why this is safer than an SSH Key for an Agent
In your "Separate Linux User" setup, using a Fine-grained PAT is superior to an SSH key for three reasons:

Repository Isolation: As you asked, it physically cannot see your other work.

API Control: SSH keys only handle Git (push/pull). A PAT allows you to precisely control what the agent does with the gh CLI (e.g., let it create PRs but not delete the repository).

Auto-Expiry: You can set the token to expire in 30 days. If you forget about the agent or the machine is compromised, the "key" eventually stops working on its own.

How to give the token to the Agent
Once you've generated the token, you don't need to type it in every time. In the agent's Linux user session:

Bash
# Set it as an environment variable in the agent's .bashrc or launch script
export GH_TOKEN=github_pat_xxxx_your_token_here

# Then the 'gh' CLI and 'git' will automatically use it
gh auth status
Comparison: Fine-grained PAT vs. SSH Deploy Key
You might also hear about Deploy Keys (which are repository-specific SSH keys). Here is how they compare for your use case:

Feature	Fine-grained PAT	SSH Deploy Key
Scope	One or many specific repos	Strictly one repo
Identity	Acts as You (restricted)	Acts as a "Machine"
CLI Tools	Works perfectly with gh CLI	Only works with git
PR Workflow	Can open/comment on PRs	Cannot easily interact with PRs
Verdict: For an "agent" that needs to use gh and participate in PRs, the Fine-grained PAT is the better choice.

Would you like me to help you generate a curl command or a script to verify a token's permissions once you've created it?