// eslint-config-next ships native flat-config arrays as of Next 16 / ESLint 9, so no
// FlatCompat shim is needed here (FlatCompat + eslint-plugin-react's own flat configs
// crash with "Converting circular structure to JSON" on this version combo).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [...nextCoreWebVitals, ...nextTypescript];

export default eslintConfig;
