import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElButton, ElInput } from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import { router } from './router'
import './styles/global.css'

// 只注册用到的两个组件：全量 use(ElementPlus) 会让产物体积多出 ~800KB。
createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElButton)
  .use(ElInput)
  .mount('#app')
