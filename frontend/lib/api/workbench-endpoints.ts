import { apiClient } from "./client";
import type {
  ApiResponse,
  WorkbenchEvent,
  WorkbenchProposal,
  WorkbenchRepository,
  WorkbenchRuntime,
  WorkbenchThread,
  WorkbenchTurn,
} from "./types";

const workbenchBase = (workspaceId: string) =>
  `/workspaces/${workspaceId}/workbench`;

export const listWorkbenchRepositories = (workspaceId: string) =>
  apiClient
    .get<ApiResponse<WorkbenchRepository[]>>(
      `${workbenchBase(workspaceId)}/repositories`,
    )
    .then((r) => r.data.data);

export const listWorkbenchRuntimes = (workspaceId: string) =>
  apiClient
    .get<ApiResponse<WorkbenchRuntime[]>>(
      `${workbenchBase(workspaceId)}/runtimes`,
    )
    .then((r) => r.data.data);

export const listWorkbenchThreads = (workspaceId: string) =>
  apiClient
    .get<ApiResponse<WorkbenchThread[]>>(
      `${workbenchBase(workspaceId)}/threads`,
    )
    .then((r) => r.data.data);

export const getWorkbenchThread = (workspaceId: string, threadId: string) =>
  apiClient
    .get<ApiResponse<WorkbenchThread>>(
      `${workbenchBase(workspaceId)}/threads/${threadId}`,
    )
    .then((r) => r.data.data);

export const createWorkbenchThread = (
  workspaceId: string,
  data: {
    repositoryId: string;
    runtimeId: string;
    requirement: string;
    requestId: string;
    title?: string;
  },
) =>
  apiClient
    .post<ApiResponse<WorkbenchThread>>(
      `${workbenchBase(workspaceId)}/threads`,
      data,
    )
    .then((r) => r.data.data);

export const createWorkbenchTurn = (
  workspaceId: string,
  threadId: string,
  data: { runtimeId: string; requirement: string; requestId: string },
) =>
  apiClient
    .post<ApiResponse<WorkbenchTurn>>(
      `${workbenchBase(workspaceId)}/threads/${threadId}/turns`,
      data,
    )
    .then((r) => r.data.data);

export const listWorkbenchEvents = (
  workspaceId: string,
  threadId: string,
  turnId: string,
  afterSequence = 0,
) =>
  apiClient
    .get<ApiResponse<WorkbenchEvent[]>>(
      `${workbenchBase(workspaceId)}/threads/${threadId}/turns/${turnId}/events`,
      { params: { afterSequence } },
    )
    .then((r) => r.data.data);

export const cancelWorkbenchTurn = (
  workspaceId: string,
  threadId: string,
  turnId: string,
) =>
  apiClient
    .post<ApiResponse<WorkbenchTurn>>(
      `${workbenchBase(workspaceId)}/threads/${threadId}/turns/${turnId}/cancel`,
    )
    .then((r) => r.data.data);

export const confirmWorkbenchProposal = (
  workspaceId: string,
  threadId: string,
  proposalId: string,
) =>
  apiClient
    .post<ApiResponse<WorkbenchProposal>>(
      `${workbenchBase(workspaceId)}/threads/${threadId}/proposals/${proposalId}/confirm`,
    )
    .then((r) => r.data.data);

export const workbenchEventStreamUrl = (
  workspaceId: string,
  threadId: string,
  turnId: string,
  afterSequence: number,
) =>
  `${workbenchBase(workspaceId)}/threads/${threadId}/turns/${turnId}/events/stream?afterSequence=${afterSequence}`;
