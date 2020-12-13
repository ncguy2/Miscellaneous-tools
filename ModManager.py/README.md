# Mod manager

This script is a simple management and deployment interface. Given a json input (dubbed "profiles"), 
it manages the whole mod installation process; downloading, staging, and deploying the mod files without any
additional user input.

Currently, it only supports mods provided by [mod.io](https://mod.io), however it should be somewhat trivial
to support other mod providers, providing they provide a comprehensive REST API.

## Configuration

Configuration is applied via `config.ini`, which is expected to be in the same directory as `main.py`.
The table below details all the currently supported configuration options

| Section | Configuration Item | Description | Default value | Notes |
| ------- | ------------------ | ----------- | ------------- | ----- |
| Core    | CACHE_DIR          | The root directory of the manager cache, where the downloads and staging is performed, and where any other data (profiles, deployment metadata, etc...) is stored. | "~/.mod.io" | While "~" expansion is supported, no other shell-isms are at this time (no environment variables, for example). |
| mod.io  | AUTH_KEY           | The authentication key for [mod.io](https://mod.io); Without this, downloads cannot be performed.

## Parameters

Each (non-`--*-dir`) parameter works on a single profile at a time. If multiple profiles are given, then each one will 
be processed in sequence. Most parameters will block a complete run (all the stages running in sequence),
though in most cases it should be sufficient to simply provide the profiles. The defaults should be fine for 99% of use cases.  

| Parameter | Aliases | Type | Description | Blocks complete run? |
| --------- | ------- | ---- | ----------- | -------------------- |
| `--cache-dir` | | switch | Prints the cache directory, useful for composing with other shell commands (such as `ls`). | Yes |
| `--download-dir` | | switch | As above, but the root download directory instead. | Yes |
| `--staging-dir` | | switch | Again, with the root staging directory. | Yes |
| `--db-dir` | | switch | And again... This time with the storage directory. | Yes |
| `--profile-dir` | | switch | What's this? One more time? With the profile directory now? Scandalous! | Yes |
|||||
| `--edit` | | switch | Opens the provided profile in the default editor (`edit`). If the profile doesn't exist, a template will be generated before anything is opened. | Yes |
| `--edit-with` | | string | As with `--edit`, but using the provided binary instead. | Yes |
| `--delete` | | switch | After confirming intentions, deletes the provided profile. | Yes |
|||||
| `--view` | `-v` | switch | Outputs the file contents of the profile. | No |
| `--force` | `-f` | switch | Tells the download step to download the file, regardless of whether the existing file is newer. | No |
| `--download` | `-D` | switch | Performs the download step (Assuming mod.io/API_KEY is set). | Yes |
| `--stage` | `-s` | switch | Performs the staging step, moving/extracting any active mod files to the staging directory in preparation for deployment. | Yes |
| `--deploy` | `-d` | switch | Performs the deployment step, moving any files within the staging directory to the mod install directory as dictated by the profile. | Yes |
| `--cleanup` | `-c` | switch | Performs the cleanup step, removing any recognised mod files from the mod install directory, and cleaning up any now-empty directories. | Yes |
|||||
| `--get` | | string | Gets the given property from the profile and prints it to stdout. If multiple profiles are given, then the profile name will also be added to distinguish each item | Yes |
| `profiles` | | list of strings | The profiles to process, Each profile name given should correspond with a .json file in the profile directory (`--profile-dir`) | No |

## Profile definition

| Field | Type | Purpose |
| ----- | ---- | ------- |
| uuid  | string | Uniquely identifying the profile. If this is null when the profile is loaded, a new uuid is generated and written to the file automatically. |
| name  | string | This is a display name, mostly used for debugging and logging. |
| id    | integer | This is the id that matches to this item on the mod provider (in this case, [mod.io](https://mod.io)). |
| install_directory | string (filepath) | This is the directory that all mods should be installed into oupon deployment. |
| mods | map | The map defining which mods should be active. |
| mods.key | string | The display name for the mod. |
| mods.value | integer | The identifier for this mod on the mod provider. |

### Sample profile

```json5
{
  "uuid": "30d416d1-7750-4538-8f73-145579103796",
  "name": "Eco",
  "id": 6,
  "install_directory": "/home/steam/games/eco/Mods",
  "mods": {
    "Party Mod": 174583
  }
}
```
