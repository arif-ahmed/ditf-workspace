# DITF Workspace

Central workspace repository that hosts the **DG TMS** component repositories as git submodules.

## Submodules

| Path | Repository | Description |
| --- | --- | --- |
| `dg-tms-api` | [DG-Infotech/dg-tms-api](https://github.com/DG-Infotech/dg-tms-api) | Backend API |
| `dg-tms-client-portal` | [DG-Infotech/dg-tms-client-portal](https://github.com/DG-Infotech/dg-tms-client-portal) | Client portal |
| `dg-tms-mobile-app` | [DG-Infotech/dg-tms-mobile-app](https://github.com/DG-Infotech/dg-tms-mobile-app) | Mobile app |
| `dg-tms-web-portal` | [DG-Infotech/dg-tms-web-portal](https://github.com/DG-Infotech/dg-tms-web-portal) | Web portal |

## Getting started

Clone this repository including its submodules:

```bash
git clone --recurse-submodules https://github.com/arif-ahmed/ditf-workspace.git
cd ditf-workspace
```

Or, from a plain clone:

```bash
git submodule update --init
```

## Working on a submodule

After cloning, enter the submodule you want to work on and run the usual git commands there:

```bash
cd dg-tms-api
git status
git pull
```

To move a submodule to the latest commit on its remote branch:

```bash
git submodule update --init --remote dg-tms-api
```

To pin a submodule to a specific commit:

```bash
git submodule set-branch --branch <branch> dg-tms-api
git submodule update --remote dg-tms-api
```
