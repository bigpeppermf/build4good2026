import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import DashboardView from "../views/DashboardView.vue";
import LoginView from "../views/LoginView.vue";
import ChatView from "../views/ChatView.vue";
import SettingsView from "../views/SettingsView.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/login", name: "login", component: LoginView },
    { path: "/dashboard", name: "dashboard", component: DashboardView },
    { path: "/chat", name: "chat", component: ChatView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
});

export default router;
