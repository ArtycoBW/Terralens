import {WorkspaceProvider} from "@/components/workspace/provider";
import {Shell} from "@/components/workspace/shell";
export default function Layout({children}:{children:React.ReactNode}){return <WorkspaceProvider><Shell>{children}</Shell></WorkspaceProvider>}
