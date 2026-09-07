const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

/** @type {import('expo/metro-config').Config} */
const config = getDefaultConfig(__dirname);

module.exports = withNativeWind(config, { input: "./global.css" });
