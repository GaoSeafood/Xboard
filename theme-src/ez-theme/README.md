# EZ_THEME for 筋斗云

This user interface is based on [EZTHEME/EZ_THEME](https://github.com/EZTHEME/EZ_THEME), upstream revision `2c0581386d86006315e6eba2f5970c923892caba`.

The upstream `package.json` declares ISC, but the checked-out upstream revision did not include a `LICENSE` file. Preserve this attribution and verify the upstream licensing terms before redistributing this source outside the project.

Local integration changes:

- Uses the XBoard panel adapter and same-origin `/api/v1` requests.
- Applies 筋斗云 site text, logo and blue theme color.
- Maps gift-card redemption to XBoard's `/user/gift-card/redeem` endpoint.
- Removes the unsupported early-cycle action and disables demo download links and browser restrictions.
- Builds into `theme/Xboard/assets/ez-theme` for the existing Laravel theme loader.

Build with Node.js 20.19.6 and npm:

```sh
npm ci --ignore-scripts
npm run build
```
