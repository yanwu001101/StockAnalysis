import type { CapacitorConfig } from '@capacitor/cli'

// Android App 壳：页面文件打进 APK，接口走绝对地址（打包时 VITE_API_BASE，或设置页里手填）。
const config: CapacitorConfig = {
  appId: 'com.stockanalysis.app',
  appName: '智能选股',
  webDir: 'dist',
  android: {
    // 局域网后端是 http，Android 9+ 默认禁明文，这里放开
    allowMixedContent: true,
  },
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
}

export default config
