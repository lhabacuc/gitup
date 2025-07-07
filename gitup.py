#!/usr/bin/env python3

import argparse
import os
import base64
import sys
import time
import threading
from github import Github
from github.GithubException import GithubException
import glob
from pathlib import Path

# Caminho para armazenar o token
TOKEN_PATH = os.path.expanduser("~/.gitup_token")

class Colors:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

def colored(text, color):
    """Aplica cor ao texto se o terminal suportar."""
    if os.getenv('NO_COLOR') or not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.RESET}"

def error(message):
    """Exibe mensagem de erro."""
    print(colored(f"gitup ERR! {message}", Colors.RED))

def success(message):
    """Exibe mensagem de sucesso."""
    print(colored(message, Colors.GREEN))

def warn(message):
    """Exibe mensagem de aviso."""
    print(colored(f"gitup WARN {message}", Colors.YELLOW))

def info(message):
    """Exibe mensagem informativa."""
    print(colored(message, Colors.CYAN))

def dim(message):
    """Exibe mensagem com cor diminuída."""
    print(colored(message, Colors.DIM))

class Spinner:
    """Spinner de loading similar ao npm."""
    def __init__(self, message="Loading"):
        self.message = message
        self.spinning = False
        self.thread = None
        self.chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.index = 0
        self.started = False

    def _spin(self):
        while self.spinning:
            try:
                char = self.chars[self.index % len(self.chars)]
                sys.stdout.write(f'\r{colored(char, Colors.CYAN)} {self.message}')
                sys.stdout.flush()
                time.sleep(0.1)
                self.index += 1
            except:
                break

    def start(self):
        if not sys.stdout.isatty():
            print(self.message)
            return
        
        if self.started:
            return
            
        self.spinning = True
        self.started = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, final_message=None):
        if not sys.stdout.isatty():
            if final_message:
                print(final_message)
            return
        
        if not self.started:
            if final_message:
                print(final_message)
            return
            
        self.spinning = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        
        # Limpar a linha do spinner
        terminal_width = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
        sys.stdout.write('\r' + ' ' * min(terminal_width, len(self.message) + 10) + '\r')
        sys.stdout.flush()
        
        if final_message:
            print(final_message)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

def get_github_client():
    """Obtém o cliente GitHub autenticado."""
    if not os.path.exists(TOKEN_PATH):
        error("Authentication required")
        print("Run: gitup login")
        print("Then provide your GitHub token when prompted")
        sys.exit(1)
    
    try:
        with open(TOKEN_PATH, 'r') as f:
            token = f.read().strip()
        return Github(token)
    except Exception as e:
        error(f"Failed to read authentication token: {e}")
        sys.exit(1)

def login(args):
    """Faz login salvando o token do GitHub."""
    print(colored("GitHub Authentication", Colors.BOLD))
    print()
    print("To authenticate, you need a GitHub personal access token.")
    print("How to get a token:")
    print("  1. Go to https://github.com/settings/tokens")
    print("  2. Click 'Generate new token (classic)'")
    print("  3. Select required permissions (repo, user)")
    print("  4. Copy the generated token")
    print()
    
    try:
        token = input("GitHub token: ").strip()
    except KeyboardInterrupt:
        print("\nCancelled")
        sys.exit(0)
    
    if not token:
        error("Token cannot be empty")
        sys.exit(1)
    
    try:
        with Spinner("Verifying token...") as spinner:
            g = Github(token)
            user = g.get_user()
            # Força uma requisição para verificar o token
            user.login
        
        with open(TOKEN_PATH, 'w') as f:
            f.write(token)
        
        success(f"Authenticated as {user.login}")
        
    except GithubException as e:
        error("Authentication failed")
        print("Please verify:")
        print("  - Token is correct")
        print("  - Token has required permissions")
        print("  - Internet connection is working")
        sys.exit(1)
    except Exception as e:
        error(f"Unexpected error: {e}")
        sys.exit(1)

def parse_repo_path(repo_path):
    """Interpreta o caminho do repositório no formato usuario/repositório:caminho."""
    if not repo_path:
        return None, None
    
    parts = repo_path.split(':', 1)
    repo_name = parts[0]
    repo_path = parts[1] if len(parts) > 1 else ""
    
    # Validar formato do repositório
    if not repo_name or '/' not in repo_name:
        return None, None
    
    return repo_name, repo_path

def send_file(args):
    """Envia um arquivo local para o repositório."""
    if not hasattr(args, 'file') or not args.file:
        error("File not specified")
        print("Usage: gitup send <local_file> <user/repo[:path]>")
        print("Example: gitup send myfile.txt user/myrepo:folder/file.txt")
        sys.exit(1)
    
    if not hasattr(args, 'repo') or not args.repo:
        error("Repository not specified")
        print("Usage: gitup send <local_file> <user/repo[:path]>")
        print("Example: gitup send myfile.txt user/myrepo:folder/file.txt")
        sys.exit(1)
    
    g = get_github_client()
    file_path, repo_path = args.file, args.repo
    repo_name, repo_file_path = parse_repo_path(repo_path)
    
    if not repo_name:
        error("Invalid repository format")
        print("Expected format: user/repo[:path]")
        print("Valid examples:")
        print("  - user/myrepo")
        print("  - user/myrepo:file.txt")
        print("  - user/myrepo:folder/file.txt")
        sys.exit(1)
    
    if not os.path.isfile(file_path):
        error(f"File not found: {file_path}")
        print("Please verify:")
        print("  - File path is correct")
        print("  - File exists")
        print("  - You have read permissions")
        sys.exit(1)
    
    spinner = Spinner(f"Connecting to {repo_name}...")
    spinner.start()
    
    try:
        repo = g.get_repo(repo_name)
        spinner.stop()
    except GithubException as e:
        spinner.stop()
        error(f"Repository not found: {repo_name}")
        print("Please verify:")
        print("  - Repository name is correct")
        print("  - You have access to the repository")
        print("  - Repository exists")
        sys.exit(1)
    
    file_name = repo_file_path or os.path.basename(file_path)
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        spinner = Spinner(f"Uploading {file_name}...")
        spinner.start()
        
        try:
            contents = repo.get_contents(file_name)
            repo.update_file(file_name, f"Update {file_name}", content, contents.sha)
            spinner.stop()
            success(f"Updated {file_name} in {repo_name}")
        except GithubException as e:
            if e.status == 404:
                repo.create_file(file_name, f"Add {file_name}", content)
                spinner.stop()
                success(f"Created {file_name} in {repo_name}")
            else:
                spinner.stop()
                error(f"Upload failed: {e}")
                print("Possible causes:")
                print("  - File too large (GitHub limit)")
                print("  - No write permission")
                print("  - Filename conflict")
                sys.exit(1)
                
    except Exception as e:
        if 'spinner' in locals():
            spinner.stop()
        error(f"Unexpected error: {e}")
        sys.exit(1)

def copy(args):
    """Copia arquivos de/para o repositório."""
    if not hasattr(args, 'src') or not args.src:
        error("Source not specified")
        print("Usage: gitup copy <source> <destination>")
        print("Examples:")
        print("  Upload: gitup copy ./folder user/repo:remote_folder")
        print("  Download: gitup copy user/repo:file.txt ./local/")
        sys.exit(1)
    
    if not hasattr(args, 'dst') or not args.dst:
        error("Destination not specified")
        print("Usage: gitup copy <source> <destination>")
        print("Examples:")
        print("  Upload: gitup copy ./folder user/repo:remote_folder")
        print("  Download: gitup copy user/repo:file.txt ./local/")
        sys.exit(1)
    
    g = get_github_client()
    src, dst = args.src, args.dst
    
    if src.startswith('.') or not ':' in src:
        # Upload: local -> remoto
        repo_name, repo_path = parse_repo_path(dst)
        
        if not repo_name:
            error("Invalid destination repository format")
            print("For upload, destination must be: user/repo[:path]")
            print("Example: gitup copy ./myfile.txt user/myrepo:folder/")
            sys.exit(1)
        
        spinner = Spinner(f"Connecting to {repo_name}...")
        spinner.start()
        
        try:
            repo = g.get_repo(repo_name)
            spinner.stop()
        except GithubException as e:
            spinner.stop()
            error(f"Repository not found: {repo_name}")
            print("Please verify:")
            print("  - Repository name is correct")
            print("  - You have access to the repository")
            sys.exit(1)
            
        src_path = Path(src)
        if not src_path.exists():
            error(f"Source not found: {src}")
            print("Please verify the file or folder path")
            sys.exit(1)
            
        if src_path.is_dir():
            files = list(src_path.rglob('*'))
            file_count = len([f for f in files if f.is_file()])
            
            spinner = Spinner(f"Uploading {file_count} files...")
            spinner.start()
            
            for file_path in files:
                if file_path.is_file():
                    rel_path = file_path.relative_to(src_path)
                    dest_path = os.path.join(repo_path, str(rel_path)).replace('\\', '/')
                    
                    try:
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        
                        try:
                            contents = repo.get_contents(dest_path)
                            repo.update_file(dest_path, f"Update {dest_path}", content, contents.sha)
                        except GithubException as e:
                            if e.status == 404:
                                repo.create_file(dest_path, f"Add {dest_path}", content)
                            else:
                                spinner.stop()
                                error(f"Failed to upload {dest_path}: {e}")
                                sys.exit(1)
                    except Exception as e:
                        spinner.stop()
                        error(f"Failed to upload {file_path}: {e}")
                        sys.exit(1)
            
            spinner.stop()
            success(f"Uploaded {file_count} files to {repo_name}")
            
        elif src_path.is_file():
            dest_path = repo_path or os.path.basename(src)
            
            spinner = Spinner(f"Uploading {dest_path}...")
            spinner.start()
            
            try:
                with open(src, 'rb') as f:
                    content = f.read()
                
                try:
                    contents = repo.get_contents(dest_path)
                    repo.update_file(dest_path, f"Update {dest_path}", content, contents.sha)
                    spinner.stop()
                    success(f"Updated {dest_path} in {repo_name}")
                except GithubException as e:
                    if e.status == 404:
                        repo.create_file(dest_path, f"Add {dest_path}", content)
                        spinner.stop()
                        success(f"Created {dest_path} in {repo_name}")
                    else:
                        spinner.stop()
                        error(f"Upload failed: {e}")
                        sys.exit(1)
            except Exception as e:
                spinner.stop()
                error(f"Upload failed: {e}")
                sys.exit(1)
        else:
            error(f"Invalid source: {src}")
            sys.exit(1)
    else:
        # Download: remoto -> local
        repo_name, repo_path = parse_repo_path(src)
        
        if not repo_name:
            error("Invalid source repository format")
            print("For download, source must be: user/repo:path")
            print("Example: gitup copy user/myrepo:file.txt ./local/")
            sys.exit(1)
        
        spinner = Spinner(f"Connecting to {repo_name}...")
        spinner.start()
        
        try:
            repo = g.get_repo(repo_name)
            spinner.stop()
        except GithubException as e:
            spinner.stop()
            error(f"Repository not found: {repo_name}")
            sys.exit(1)
        
        spinner = Spinner(f"Downloading from {repo_path}...")
        spinner.start()
        
        try:
            contents = repo.get_contents(repo_path)
            
            if isinstance(contents, list):
                os.makedirs(dst, exist_ok=True)
                file_count = len(contents)
                
                for content in contents:
                    if content.type == 'file':
                        file_content = base64.b64decode(content.content)
                        local_path = os.path.join(dst, content.name)
                        with open(local_path, 'wb') as f:
                            f.write(file_content)
                
                spinner.stop()
                success(f"Downloaded {file_count} files to {dst}")
            else:
                file_content = base64.b64decode(contents.content)
                local_path = os.path.join(dst, contents.name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(file_content)
                
                spinner.stop()
                success(f"Downloaded {contents.name} to {local_path}")
                
        except GithubException as e:
            spinner.stop()
            error(f"Download failed: {e}")
            print("Please verify:")
            print("  - File/folder path is correct")
            print("  - File/folder exists in repository")
            print("  - You have access to the content")
            sys.exit(1)

def remove_file(args):
    """Remove um arquivo do repositório."""
    if not hasattr(args, 'file') or not args.file:
        error("File not specified")
        print("Usage: gitup rm <user/repo:path>")
        print("Example: gitup rm user/myrepo:file.txt")
        sys.exit(1)
    
    g = get_github_client()
    repo_name, repo_path = parse_repo_path(args.file)
    
    if not repo_name:
        error("Invalid repository format")
        print("Expected format: user/repo:path")
        print("Example: gitup rm user/myrepo:file.txt")
        sys.exit(1)
    
    if not repo_path:
        error("File path not specified")
        print("You must specify which file to remove")
        print("Example: gitup rm user/myrepo:file.txt")
        sys.exit(1)
    
    spinner = Spinner(f"Connecting to {repo_name}...")
    spinner.start()
    
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(repo_path)
        
        if isinstance(contents, list):
            spinner.stop()
            error(f"Cannot remove directory: {repo_path}")
            print("You must specify a file to remove")
            sys.exit(1)
        
        spinner.stop()
        spinner = Spinner(f"Removing {repo_path}...")
        spinner.start()
        
        repo.delete_file(repo_path, f"Remove {repo_path}", contents.sha)
        spinner.stop()
        success(f"Removed {repo_path} from {repo_name}")
        
    except GithubException as e:
        spinner.stop()
        if e.status == 404:
            error(f"File not found: {repo_path}")
            print("Please verify:")
            print("  - File path is correct")
            print("  - File exists in repository")
        else:
            error(f"Remove failed: {e}")
            print("Please verify:")
            print("  - You have delete permissions")
            print("  - Repository is accessible")
        sys.exit(1)

def list_files(args):
    """Lista arquivos no repositório ou repositórios do usuário."""
    g = get_github_client()
    
    repo_arg = args.repo if hasattr(args, 'repo') and args.repo else ":."
    
    if repo_arg == ':.':
        # Lista todos os repositórios do usuário autenticado
        spinner = Spinner("Fetching repositories...")
        spinner.start()
        
        try:
            user = g.get_user()
            repos = user.get_repos()
            repo_list = list(repos)
            
            spinner.stop()
            
            if not repo_list:
                info("No repositories found")
                return
            
            print(f"Repositories for {colored(user.login, Colors.BOLD)}:")
            for repo in repo_list:
                visibility = colored("private", Colors.YELLOW) if repo.private else colored("public", Colors.GREEN)
                print(f"  {repo.full_name} ({visibility})")
                
        except GithubException as e:
            spinner.stop()
            error(f"Failed to fetch repositories: {e}")
            sys.exit(1)
    else:
        # Lista arquivos no repositório especificado
        repo_name, repo_path = parse_repo_path(repo_arg)
        
        if not repo_name:
            error("Invalid repository format")
            print("Valid formats:")
            print("  gitup ls :.                    (list your repositories)")
            print("  gitup ls user/repo             (list repository root)")
            print("  gitup ls user/repo:folder      (list specific folder)")
            sys.exit(1)
        
        spinner = Spinner(f"Fetching contents from {repo_name}...")
        spinner.start()
        
        try:
            repo = g.get_repo(repo_name)
            contents = repo.get_contents(repo_path)
            
            spinner.stop()
            
            path_display = repo_path or "/"
            print(f"Contents of {colored(f'{repo_name}:{path_display}', Colors.BOLD)}:")
            
            if isinstance(contents, list):
                for content in contents:
                    icon = "📁" if content.type == 'dir' else "📄"
                    type_color = Colors.BLUE if content.type == 'dir' else Colors.WHITE
                    print(f"  {icon} {colored(content.name, type_color)}")
            else:
                icon = "📁" if contents.type == 'dir' else "📄"
                type_color = Colors.BLUE if contents.type == 'dir' else Colors.WHITE
                print(f"  {icon} {colored(contents.name, type_color)}")
                
        except GithubException as e:
            spinner.stop()
            if e.status == 404:
                error(f"Repository or path not found: {repo_name}:{repo_path}")
                print("Please verify:")
                print("  - Repository name is correct")
                print("  - Path exists in repository")
                print("  - You have access to the repository")
            else:
                error(f"Failed to list files: {e}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="GitHub CLI tool for simple repository management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gitup login                                    # Authenticate with GitHub
  gitup ls :.                                    # List your repositories
  gitup ls user/repo                             # List files in repository root
  gitup ls user/repo:folder                      # List files in folder
  gitup send file.txt user/repo                  # Upload file to root
  gitup send file.txt user/repo:folder/          # Upload file to folder
  gitup copy ./folder user/repo:remote_folder    # Upload entire folder
  gitup copy user/repo:file.txt ./local/         # Download file
  gitup rm user/repo:file.txt                    # Remove file

Repository format: user/repository[:path]
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Login
    login_parser = subparsers.add_parser("login", help="Authenticate with GitHub")
    login_parser.set_defaults(func=login)

    # Send
    send_parser = subparsers.add_parser("send", help="Upload file to repository")
    send_parser.add_argument("file", help="Local file path")
    send_parser.add_argument("repo", help="Repository in format user/repo[:path]")
    send_parser.set_defaults(func=send_file)

    # Copy
    copy_parser = subparsers.add_parser("copy", help="Copy files to/from repository")
    copy_parser.add_argument("src", help="Source (local or user/repo:path)")
    copy_parser.add_argument("dst", help="Destination (local or user/repo:path)")
    copy_parser.set_defaults(func=copy)

    # Remove
    rm_parser = subparsers.add_parser("rm", help="Remove file from repository")
    rm_parser.add_argument("file", help="File in format user/repo:path")
    rm_parser.set_defaults(func=remove_file)

    # List
    ls_parser = subparsers.add_parser("ls", help="List files in repository")
    ls_parser.add_argument("repo", help="Repository in format user/repo[:path]", nargs="?", default=":.")
    ls_parser.set_defaults(func=list_files)

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
    else:
        error("No command specified")
        print("Available commands: login, send, copy, rm, ls")
        print("Use 'gitup --help' for more information")
        parser.print_help()

if __name__ == "__main__":
    main()
