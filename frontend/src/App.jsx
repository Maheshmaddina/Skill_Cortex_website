import { Route, Routes } from "react-router";

import RequireAuth from "./auth/RequireAuth.jsx";
import AdminLayout from "./components/AdminLayout.jsx";
import Layout from "./components/Layout.jsx";
import AdminBookings from "./pages/admin/AdminBookings.jsx";
import AdminDashboard from "./pages/admin/AdminDashboard.jsx";
import AdminDepartments from "./pages/admin/AdminDepartments.jsx";
import AdminNotifications from "./pages/admin/AdminNotifications.jsx";
import AdminPayments from "./pages/admin/AdminPayments.jsx";
import AdminReminderRules from "./pages/admin/AdminReminderRules.jsx";
import AdminLearnerSessions from "./pages/admin/AdminLearnerSessions.jsx";
import AdminSlots from "./pages/admin/AdminSlots.jsx";
import AdminUsers from "./pages/admin/AdminUsers.jsx";
import AdminWebinarForm from "./pages/admin/AdminWebinarForm.jsx";
import AdminWebinars from "./pages/admin/AdminWebinars.jsx";
import BookingDetail from "./pages/BookingDetail.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import MyBookings from "./pages/MyBookings.jsx";
import NotFound from "./pages/NotFound.jsx";
import Notifications from "./pages/Notifications.jsx";
import Profile from "./pages/Profile.jsx";
import Register from "./pages/Register.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import WebinarDetail from "./pages/WebinarDetail.jsx";
import Webinars from "./pages/Webinars.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="webinars" element={<Webinars />} />
        <Route path="webinars/:webinarId" element={<WebinarDetail />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="reset-password" element={<ResetPassword />} />

        <Route element={<RequireAuth role="USER" />}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="bookings" element={<MyBookings />} />
          <Route path="bookings/:bookingId" element={<BookingDetail />} />
          <Route path="notifications" element={<Notifications />} />
        </Route>
        <Route element={<RequireAuth />}>
          <Route path="profile" element={<Profile />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Route>

      <Route
        path="admin"
        element={
          <RequireAuth role="ADMIN">
            <AdminLayout />
          </RequireAuth>
        }
      >
        <Route index element={<AdminDashboard />} />
        <Route path="departments" element={<AdminDepartments />} />
        <Route path="webinars" element={<AdminWebinars />} />
        <Route path="webinars/new" element={<AdminWebinarForm />} />
        <Route path="webinars/:webinarId/edit" element={<AdminWebinarForm />} />
        <Route path="webinars/:webinarId/slots" element={<AdminSlots />} />
        <Route path="learner-webinars" element={<AdminLearnerSessions />} />
        <Route path="bookings" element={<AdminBookings />} />
        <Route path="payments" element={<AdminPayments />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="notifications" element={<AdminNotifications />} />
        <Route path="reminders" element={<AdminReminderRules />} />
      </Route>
    </Routes>
  );
}
