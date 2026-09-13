import { Routes, Route } from 'react-router'
import Home from './pages/Home'
import ResetPassword from './pages/ResetPassword'
import ViewQuote from './pages/ViewQuote'
import ViewInvoice from './pages/ViewInvoice'
import BlogIndex from './pages/blog/BlogIndex'
import BlogPost from './pages/blog/BlogPost'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/quote/:token" element={<ViewQuote />} />
      <Route path="/invoice/:token" element={<ViewInvoice />} />
      <Route path="/blog" element={<BlogIndex />} />
      <Route path="/blog/:slug" element={<BlogPost />} />
    </Routes>
  )
}
