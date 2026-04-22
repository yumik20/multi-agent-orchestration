      const strengthClass = strength === "secondary" ? "posting-window-secondary" : "";
      const strengthLabel = strength === "secondary" ? "Secondary" : "Prime";
      const payload = encodeURIComponent(JSON.stringify({ ...win, day, platformLabel: label, strength: strengthLabel }));
      return `<button type="button" class="posting-window posting-window-${escapeHtml(win.platform)} ${strengthClass}" style="top:${top}%;height:${height}%;" title="${escapeHtml(`${label} ${strengthLabel.toLowerCase()} window · ${win.start}–${win.end} ET — click for details`)}" data-posting-window="${payload}"><span class="posting-window-tag">${escapeHtml(label)}${strength === "secondary" ? `<span class="posting-window-tag-mark">2°</span>` : ""}</span></button>`;
    })
    .join("");
}

function renderScheduleCalendar(weeklySchedule, options = {}) {
  const days = options.days || weeklySchedule?.days || [];
  const calendar = weeklySchedule?.calendar || {};
  const scheduleStartMin = Number(weeklySchedule?.dayStartMin ?? 8 * 60);
  const scheduleEndMin = Number(weeklySchedule?.dayEndMin ?? 21 * 60);
  const dayStartMin = Number(options.windowStartMin ?? scheduleStartMin);
  const dayEndMin = Number(options.windowEndMin ?? scheduleEndMin);
  const currentTimeMin = Number(weeklySchedule?.currentTimeMin ?? -1);
  const todayIndex = Number(weeklySchedule?.todayIndex ?? -1);
  const totalMinutes = Math.max(60, dayEndMin - dayStartMin);
  const ticks = buildTimeTicks(dayStartMin, dayEndMin);
  const hourHeight = Number(options.hourHeight ?? 56);
  const canvasHeight = Math.max(420, Math.round((totalMinutes / 60) * hourHeight));
  const columnMinWidth = Number(options.columnMinWidth ?? (days.length === 1 ? 0 : 244));
  const viewportHeight = Number(options.viewportHeight ?? 0);
  const compactCards = Boolean(options.compactCards);
  const gridTemplateColumns =
    days.length === 1
      ? "minmax(0, 1fr)"
      : `repeat(${Math.max(days.length, 1)}, minmax(${columnMinWidth}px, ${columnMinWidth}px))`;
  const scrollId = options.scrollId || "";
  const scrollAttrs = scrollId ? `id="${escapeHtml(scrollId)}"` : "";
  const viewportAttrs = scrollId ? `data-schedule-scroll-id="${escapeHtml(scrollId)}"` : "";

  const timeRail = `
    <div class="schedule-time-rail" style="grid-template-rows: 28px repeat(${ticks.length}, ${hourHeight}px);">
      <div class="schedule-time-spacer"></div>
      ${ticks.map((minute) => `<div class="schedule-time-label">${escapeHtml(formatMinutesLabel(minute))}</div>`).join("")}
    </div>
  `;

  const dayColumns = days
    .map((day, index) => {
      const isToday = index === todayIndex;
      const events = calendar[day] || [];
      const eventBlocks = events
        .map((event) => {
          const actualStartMin = Number(event.startMin || 0);
          const actualEndMin = Number(event.endMin || actualStartMin);
          const clippedStartMin = Math.max(actualStartMin, dayStartMin);
          const clippedEndMin = Math.min(actualEndMin, dayEndMin);
          if (clippedEndMin <= dayStartMin || clippedStartMin >= dayEndMin || clippedEndMin <= clippedStartMin) {
            return "";
          }
          const topPct = ((clippedStartMin - dayStartMin) / totalMinutes) * 100;
          const heightPct = ((clippedEndMin - clippedStartMin) / totalMinutes) * 100;
          const laneCount = Math.max(1, Number(event.laneCount || 1));
          const laneIndex = Number(event.laneIndex || 0);
          const gapPx = 10;
          const eventAreaLeft = 30;
          const eventAreaWidth = 100 - eventAreaLeft;
          const widthCalc = `calc((${eventAreaWidth}% - ${(laneCount - 1) * gapPx}px) / ${laneCount})`;
          const leftCalc = laneCount === 1
            ? `${eventAreaLeft}%`
            : `calc(${eventAreaLeft}% + (${widthCalc} + ${gapPx}px) * ${laneIndex})`;
          const isClippedStart = actualStartMin < dayStartMin;
          const isClippedEnd = actualEndMin > dayEndMin;
          const timeLabel = `${formatMinutesLabel(actualStartMin)} - ${formatMinutesLabel(actualEndMin)}`;
          const contextLabel = event.team || (event.isActiveNow ? "Active now" : "");
          const compactTaskTitle = compactText(event.task || "", 30);
          const densityClass = compactCards
            ? heightPct < 5.2
              ? "is-tiny"
              : heightPct < 8.5
                ? "is-tight"
                : "is-regular"
            : "";
          const detailPayload = encodeURIComponent(JSON.stringify({
            ...event,
            day,
            timeRange: timeLabel,
            context: contextLabel,
          }));
          const botSlug = String(event.bot || "").toLowerCase().replace(/[^a-z0-9]/g, "");
          const botColorClass = botSlug ? `schedule-event-bot-${botSlug}` : "";
          return `
            <button
              type="button"
              class="schedule-event ${botColorClass} ${compactCards ? `schedule-event-compact ${densityClass}` : ""} ${event.bot === "Manager" ? "schedule-event-core" : ""} ${event.isActiveNow ? "is-active-now" : ""} ${isClippedStart ? "is-clipped-start" : ""} ${isClippedEnd ? "is-clipped-end" : ""}"
              style="top:${topPct}%;height:${Math.max(heightPct, 3.8)}%;width:${widthCalc};left:${leftCalc};"
              title="${escapeHtml(`${event.bot} · ${event.task} · ${timeLabel}`)}"
              data-schedule-event="${detailPayload}"
            >
              <div class="schedule-event-time">${escapeHtml(compactCards ? event.time : timeLabel)}</div>
              <div class="schedule-event-bot">${escapeHtml(event.bot)}</div>
              <div class="schedule-event-task">${escapeHtml(compactCards ? compactTaskTitle : event.task)}</div>
              ${!compactCards && contextLabel ? `<div class="schedule-event-context">${escapeHtml(contextLabel)}</div>` : ""}
            </button>
          `;
        })
        .join("");
      const hourLines = ticks
        .map((minute) => {
          const topPct = ((minute - dayStartMin) / totalMinutes) * 100;
          return `<div class="schedule-hour-line" style="top:${topPct}%;"></div>`;
        })
        .join("");
      const nowLine = isToday && currentTimeMin >= dayStartMin && currentTimeMin <= dayEndMin
        ? `<div class="schedule-now-line" style="top:${((currentTimeMin - dayStartMin) / totalMinutes) * 100}%;">
            <span class="schedule-now-label">Now</span>
          </div>`
        : "";
      return `
        <section class="planner-day ${isToday ? "planner-day-today" : ""}" data-day-index="${index}">
          <div class="planner-day-head">
            <span>${escapeHtml(day)}</span>
            ${isToday ? `<span class="planner-today-label">Today</span>` : ""}
          </div>
          <div class="schedule-day-canvas" style="height:${canvasHeight}px;">
            ${renderPostingWindowBands(day, dayStartMin, dayEndMin, totalMinutes)}
            ${hourLines}
            ${nowLine}
            ${eventBlocks || `<div class="schedule-empty-note">No schedule</div>`}
          </div>
        </section>
      `;
    })
    .join("");

  return `
    <div class="schedule-viewport" ${viewportAttrs} ${viewportHeight ? `style="max-height:${viewportHeight}px;"` : ""}>
      <div class="schedule-calendar">
        ${timeRail}
        <div class="schedule-grid-scroll" ${scrollAttrs}>
          <div class="planner-grid" style="grid-template-columns:${gridTemplateColumns};">
