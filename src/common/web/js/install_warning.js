const DOCS_URL = "https://docs.warpedpinball.com/guides/";

// Where each board family's reset clip pictures are in the install guide.
// The firmware build cannot tell System 9 from System 11, so sys11 also
// points at the System 9 guide.
const RESET_CLIP_DOCS = {
  wpc: [{ label: "WPC reset clip locations", url: "wpc/manual/#reset-clip" }],
  sys11: [
    {
      label: "System 11 reset clip location",
      url: "system11/manual/#reset-clip",
    },
    {
      label: "System 9 reset clip location",
      url: "system9/manual/#reset-clip",
    },
  ],
  classic: [
    {
      label: "Bally / Stern reset clip location",
      url: "classic/manual/#reset-clip",
    },
  ],
  data_east: [
    {
      label: "Data East hardware installation",
      url: "data_east/manual/#hardware-installation",
    },
  ],
};

async function board_system() {
  try {
    const response = await fetch("/api/version");
    const data = await response.json();
    return data.system || null;
  } catch (e) {
    console.log("Could not read board system:", e);
    return null;
  }
}

// Early bus activity means the game's processor ran before Vector let go of
// reset, which is almost always the white reset clip being loose or on the
// wrong point. Tell the user that and link the pictures for their board.
async function show_reset_line_help() {
  const help = document.getElementById("fault_help");
  if (!help) return;

  help.textContent =
    "Early Bus Activity usually means the reset line is not connected. " +
    "Check that the white reset clip is firmly attached to the correct point on your board.";

  const links = RESET_CLIP_DOCS[await board_system()] || [];
  if (links.length > 0) {
    help.append(" See where it goes: ");
    links.forEach((link, i) => {
      if (i > 0) help.append(" or ");
      const a = document.createElement("a");
      a.href = DOCS_URL + link.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = link.label;
      help.appendChild(a);
    });
    help.append(".");
  }
  help.hidden = false;
}

async function fault_check() {
  const response = await fetch("/api/fault");
  if (response.status !== 200) {
    // Use strict equality check
    alert(
      "Something has gone wrong while checking for installation issues. Refresh the page and if the issue persists please contact inventingfun@gmail.com",
    );
  }
  const data = await response.json(); // list of faults as ["fault1", "fault2", ...]

  const modal_element = document.getElementById("install_warning_modal");
  if (data.length > 0) {
    const fault_list = document.getElementById("fault_list");
    fault_list.innerHTML = ""; // Clear any existing faults

    // Create a list item for each fault and append it to the fault_list
    data.forEach((fault) => {
      const fault_item = document.createElement("div");
      fault_item.textContent = fault;
      fault_list.appendChild(fault_item);
    });

    if (data.some((fault) => fault.startsWith("HDWR01"))) {
      await show_reset_line_help();
    }

    modal_element.setAttribute("open", ""); // Add the "open" attribute to the dialog
    console.log("Installation fault detected");
  } else {
    console.log("No installation fault:", data);
  }
}

fault_check();
