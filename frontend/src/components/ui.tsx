import Link from "next/link";
export function Empty({ children }: { children: React.ReactNode }) { return <p className="empty">{children}</p>; }
export function Failure({ message, retry }: { message: string; retry: () => void }) {
  return <div className="error-box" role="alert"><p>{message}</p><button className="secondary" onClick={retry}>Try again</button></div>;
}
export function ComingNext({ title, description }: { title: string; description: string }) {
  return <section className="placeholder panel"><span className="badge">Coming next</span><h1>{title}</h1><p>{description}</p><p>This area is planned for a later phase. Explore your university’s current data on the dashboard.</p><Link className="button" href="/dashboard">Back to dashboard <span aria-hidden="true">→</span></Link></section>;
}
