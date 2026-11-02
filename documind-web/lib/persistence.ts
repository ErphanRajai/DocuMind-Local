import type { Workspace } from "./types";
import { api } from "./api";
import { restoreWorkspaces } from "./workspaces";

export function mergeWorkspaceCopies(remote:Workspace[],local:Workspace[],deletedIds:string[]=[]) {
  const merged=[...remote];
  for(const workspace of local){
    if(deletedIds.includes(workspace.id))continue;
    const saved=remote.find(w=>w.id===workspace.id);
    if(!saved){merged.push(workspace);continue;}
    const content=(w:Workspace)=>JSON.stringify({title:w.title,documents:w.documents.map(d=>d.id),messages:w.messages});
    if(content(saved)!==content(workspace))merged.push({...workspace,id:crypto.randomUUID(),title:workspace.title.slice(0,238)+' (browser copy)',updated:Date.now()});
  }
  return merged;
}

export async function loadSavedWorkspaces(): Promise<{
  values: Workspace[];
  revisions: Record<string, number>;
  deletedIds: string[];
}> {
  const [saved,deleted] = await Promise.all([api<(Workspace & {revision:number})[]>('/summarizer/workspaces'),api<string[]>('/summarizer/workspaces/deleted').catch(()=>[])]);
  if (!Array.isArray(saved))
    throw new Error("Workspace storage returned an invalid response");
  return {
    values: restoreWorkspaces(JSON.stringify(saved)),
    revisions: Object.fromEntries(saved.map((w) => [w.id, w.revision])),
    deletedIds:Array.isArray(deleted)?deleted:[],
  };
}

export async function persistWorkspace(
  workspace: Workspace,
  revision?: number,
) {
  return api<{ revision: number }>(
    `/summarizer/workspaces/${encodeURIComponent(workspace.id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace, revision }),
    },
  );
}

export function downloadText(
  name: string,
  content: string,
  type = "text/plain",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
