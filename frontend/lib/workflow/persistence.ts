import type { WorkflowProject, WorkflowProjectNode } from './schema'

export function persistableWorkflowProject(project: WorkflowProject): WorkflowProject {
  const persistableNode = (node: WorkflowProjectNode): WorkflowProjectNode => {
    const ui = { ...(node.ui ?? {}) }
    delete ui.runtimeCapability
    return {
      ...node,
      ...(node.ui ? { ui } : {}),
      ...(node.internals
        ? {
            internals: {
              ...node.internals,
              nodes: node.internals.nodes.map((item) =>
                persistableNode(item as WorkflowProjectNode),
              ),
            },
          }
        : {}),
    }
  }
  return { ...project, nodes: project.nodes.map(persistableNode) }
}
