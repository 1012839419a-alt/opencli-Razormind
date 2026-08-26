"use client";

/*
 * SmoothUI AI Task List
 * Source: https://smoothui.dev/docs/components/ai-task-list
 * Copyright (c) 2024 Eduardo Calvo — MIT; see ../LICENSE.
 * Adapted with blocked/partial states and raw-detail slots for workflow traces.
 */

import { cn } from "@/lib/utils";
import { motion, useReducedMotion } from "motion/react";
import { Fragment, type ReactNode } from "react";

const SPRING_DEFAULT = {
  bounce: 0.1,
  duration: 0.25,
  type: "spring" as const,
};
const EASE_IN_OUT = [0.645, 0.045, 0.355, 1] as const;
const CHECK_PATH = "M 3.5 7.5 L 6 10 L 10.5 4.5";
const BOX_SIZE = 14;
const UNDERLINE_SECONDS = 1.4;

export type AITaskStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "blocked"
  | "partial";

export type AITask = {
  /** Nested sub-steps, one level. */
  children?: AITask[];
  /** Optional operational detail retained under the summary row. */
  details?: ReactNode;
  id: string;
  label: string;
  /** Short right-aligned note, e.g. "12/12" or "3 files". */
  note?: string;
  status: AITaskStatus;
};

export type AITaskListProps = {
  className?: string;
  /** Heading text. The counts are derived, never passed in. */
  label?: string;
  tasks: AITask[];
};

const flatten = (tasks: AITask[]): AITask[] =>
  tasks.flatMap((task) => [task, ...flatten(task.children ?? [])]);

const SUCCESS_COLOR = "oklch(72% 0.17 150)";
const DANGER_COLOR = "oklch(63% 0.21 25)";
const WARNING_COLOR = "oklch(75% 0.16 75)";
const INFO_COLOR = "oklch(68% 0.14 240)";

const STATUS_LABELS: Record<AITaskStatus, string> = {
  pending: "已记录",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  blocked: "阻塞",
  partial: "部分完成",
};

const boxStroke = (status: AITaskStatus): string => {
  if (status === "failed") {
    return DANGER_COLOR;
  }
  if (status === "done") {
    return SUCCESS_COLOR;
  }
  if (status === "blocked") {
    return WARNING_COLOR;
  }
  if (status === "partial") {
    return INFO_COLOR;
  }
  return "currentColor";
};

const TaskBox = ({
  status,
  shouldReduceMotion,
}: {
  shouldReduceMotion: boolean;
  status: AITaskStatus;
}) => {
  const isDone = status === "done";
  const isFailed = status === "failed";
  const isBlocked = status === "blocked";
  const isPartial = status === "partial";

  return (
    <span className="mt-0.5 flex size-3.5 shrink-0 items-center justify-center">
      <svg
        aria-hidden="true"
        className="size-3.5"
        viewBox={`0 0 ${BOX_SIZE} ${BOX_SIZE}`}
      >
        <motion.rect
          animate={{
            fillOpacity: isDone || isBlocked || isPartial ? 0.12 : 0,
            stroke: boxStroke(status),
          }}
          fill={
            isFailed
              ? DANGER_COLOR
              : isBlocked
                ? WARNING_COLOR
                : isPartial
                  ? INFO_COLOR
                  : SUCCESS_COLOR
          }
          height={12}
          rx={3.5}
          strokeWidth={1.4}
          transition={shouldReduceMotion ? { duration: 0 } : { duration: 0.2 }}
          width={12}
          x={1}
          y={1}
        />
        {isDone && (
          // Drawn, not faded: a check that draws itself reads as the act of
          // ticking the box rather than a state that was always there.
          <path
            className="ai-task-draw"
            d={CHECK_PATH}
            fill="none"
            pathLength={1}
            stroke={SUCCESS_COLOR}
            strokeDasharray="1 1"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.8}
          />
        )}
        {isFailed && (
          <path
            className="ai-task-draw"
            d="M 5 5 L 9 9 M 9 5 L 5 9"
            fill="none"
            pathLength={1}
            stroke={DANGER_COLOR}
            strokeDasharray="1 1"
            strokeLinecap="round"
            strokeWidth={1.8}
          />
        )}
        {isBlocked && (
          <path
            d="M 5 4.5 L 5 9.5 M 9 4.5 L 9 9.5"
            fill="none"
            stroke={WARNING_COLOR}
            strokeLinecap="round"
            strokeWidth={1.6}
          />
        )}
        {isPartial && (
          <path
            d="M 4.5 7 L 9.5 7"
            fill="none"
            stroke={INFO_COLOR}
            strokeLinecap="round"
            strokeWidth={1.8}
          />
        )}
      </svg>
    </span>
  );
};

const TaskRow = ({
  depth,
  shouldReduceMotion,
  task,
}: {
  depth: number;
  shouldReduceMotion: boolean;
  task: AITask;
}) => {
  const isRunning = task.status === "running";
  const isDone = task.status === "done";

  return (
    <motion.li
      // Completed rows settle down a pixel and lose a little contrast: they go
      // quiet so whatever is running is the only thing asking for attention.
      animate={{
        opacity: isDone ? 0.65 : 1,
        y: isDone && !shouldReduceMotion ? 1 : 0,
      }}
      className="list-none"
      style={{ paddingLeft: depth * 20 }}
      transition={shouldReduceMotion ? { duration: 0 } : SPRING_DEFAULT}
    >
      <span className="relative flex items-start gap-2 py-1">
        <TaskBox shouldReduceMotion={shouldReduceMotion} status={task.status} />
        <span className="sr-only">状态：{STATUS_LABELS[task.status]}。</span>

        <span className="min-w-0 flex-1 text-foreground text-sm leading-snug [overflow-wrap:anywhere]">
          {task.label}
        </span>

        {task.note ? (
          <span className="shrink-0 text-muted-foreground text-xs tabular-nums">
            {task.note}
          </span>
        ) : null}

        {isRunning && !shouldReduceMotion && (
          // A travelling underline under the active row only. One moving thing
          // at a time is what makes "which step is live" readable at a glance.
          <motion.span
            animate={{ backgroundPositionX: ["0%", "200%"] }}
            className="pointer-events-none absolute inset-x-0 bottom-0 h-px"
            style={{
              backgroundImage:
                "linear-gradient(90deg, transparent 0%, currentColor 50%, transparent 100%)",
              backgroundSize: "50% 100%",
              opacity: 0.5,
            }}
            transition={{
              duration: UNDERLINE_SECONDS,
              ease: EASE_IN_OUT,
              repeat: Number.POSITIVE_INFINITY,
            }}
          />
        )}
      </span>
      {task.details ? (
        <div className="ml-[22px] pb-1 text-xs text-muted-foreground">
          {task.details}
        </div>
      ) : null}
    </motion.li>
  );
};

/**
 * A plan an agent works through.
 *
 * Header counts are derived from the tasks, so the summary can never disagree
 * with the rows — a "3/7" that has drifted from what is on screen destroys trust
 * in the whole panel.
 */
const AITaskList = ({ className, label = "Plan", tasks }: AITaskListProps) => {
  const shouldReduceMotion = Boolean(useReducedMotion());
  const all = flatten(tasks);
  const done = all.filter((task) => task.status === "done").length;

  return (
    <div
      className={cn(
        "w-full rounded-xl border border-border bg-background p-3",
        className
      )}
    >
      <div className="mb-1.5 flex items-baseline justify-between">
        <p className="font-medium text-foreground text-sm">{label}</p>
        <p className="text-muted-foreground text-xs tabular-nums">
          {done}/{all.length}
        </p>
      </div>

      <style>{`
        .ai-task-draw { stroke-dashoffset: 0; }
        @media (prefers-reduced-motion: no-preference) {
          .ai-task-draw {
            animation: ai-task-draw 200ms cubic-bezier(0.23, 1, 0.32, 1) both;
          }
        }
        @keyframes ai-task-draw {
          from { stroke-dashoffset: 1; }
          to { stroke-dashoffset: 0; }
        }
      `}</style>

      <ul className="list-none">
        {tasks.map((task) => (
          <Fragment key={task.id}>
            <TaskRow
              depth={0}
              shouldReduceMotion={shouldReduceMotion}
              task={task}
            />
            {task.children?.map((child) => (
              <TaskRow
                depth={1}
                key={child.id}
                shouldReduceMotion={shouldReduceMotion}
                task={child}
              />
            ))}
          </Fragment>
        ))}
      </ul>
    </div>
  );
};

export default AITaskList;
