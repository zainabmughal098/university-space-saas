import { screen, within, fireEvent } from "@testing-library/react";

export function installDialogMock(dom) {
  globalThis.requestAnimationFrame = callback => { callback(); return 0; };
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  dom.window.HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
}

export function selectCalendar(label, iso) {
  const trigger = screen.getAllByRole("button").find(button => button.getAttribute("aria-haspopup") === "dialog" && button.textContent && button.getAttribute("aria-labelledby")?.split(" ").some(id => document.getElementById(id)?.textContent === label));
  if (!trigger) throw new Error(`Calendar not found: ${label}`);
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog");
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const target = Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;
  for (let attempt = 0; attempt < 240; attempt++) {
    const [month, year] = dialog.querySelector(".calendar-month strong").textContent.split(" ");
    const current = Number(year) * 12 + months.indexOf(month);
    if (target === current) break;
    fireEvent.click(within(dialog).getByRole("button", { name: current < target ? "Next month" : "Previous month" }));
  }
  const day = dialog.querySelector(`[data-date="${iso}"]`);
  if (!day) throw new Error(`Calendar day not found: ${iso}`);
  fireEvent.click(day);
}
