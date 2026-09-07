module.exports = {
  presets: [
    "babel-preset-expo",
    ["react-native-css-interop/babel", { nativewind: true }],
  ],
  plugins: ["react-native-reanimated/plugin"],
};
