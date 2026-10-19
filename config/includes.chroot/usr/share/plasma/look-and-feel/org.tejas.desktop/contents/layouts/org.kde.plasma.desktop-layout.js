// TEJAS default desktop: sky wallpaper, slim glass top bar, floating centred dock.
// Plasma runs this once, the first time a user logs in.

function trySet(obj, key, value) {
    try { obj[key] = value; } catch (e) { print("TEJAS layout: could not set " + key); }
}

// Wallpaper
var all = desktops();
for (var i = 0; i < all.length; i++) {
    var d = all[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file:///usr/share/wallpapers/TEJAS-Morning/");
    d.writeConfig("FillMode", "2");
}

// Top bar: TEJAS menu on the left, clock in the middle, status on the right.
var top = new Panel;
top.location = "top";
top.height = Math.round(gridUnit * 2);
trySet(top, "floating", true);
trySet(top, "opacity", "translucent");

var menu = top.addWidget("org.kde.plasma.kickoff");
menu.currentConfigGroup = ["General"];
menu.writeConfig("icon", "tejas-logo");
menu.writeConfig("favoritesDisplay", "0");

top.addWidget("org.kde.plasma.panelspacer");
var clock = top.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", "true");
clock.writeConfig("dateFormat", "custom");
clock.writeConfig("customDateFormat", "ddd d MMM");
clock.writeConfig("dateDisplayFormat", "BesideTime");
top.addWidget("org.kde.plasma.panelspacer");
top.addWidget("org.kde.plasma.systemtray");

// Dock: floating, centred, sized to its icons, with the all-apps grid in the middle.
var dock = new Panel;
dock.location = "bottom";
dock.height = Math.round(gridUnit * 3.4);
trySet(dock, "floating", true);
trySet(dock, "lengthMode", "fit");
trySet(dock, "alignment", "center");
trySet(dock, "opacity", "translucent");
trySet(dock, "hiding", "dodgewindows");

function pinned(apps) {
    var t = dock.addWidget("org.kde.plasma.icontasks");
    t.currentConfigGroup = ["General"];
    t.writeConfig("launchers", apps.map(function (a) { return "applications:" + a; }).join(","));
    t.writeConfig("showOnlyCurrentDesktop", "false");
    t.writeConfig("groupedTaskVisualization", "1");
    return t;
}

pinned([
    "firefox-esr.desktop",
    "org.kde.dolphin.desktop",
    "thunderbird.desktop",
    "libreoffice-writer.desktop",
    "org.inkscape.Inkscape.desktop",
    "org.kde.kdenlive.desktop",
    "org.kde.elisa.desktop",
    "org.kde.discover.desktop",
    "tejas-bridge.desktop",
    "systemsettings.desktop"
]);

var grid = dock.addWidget("org.kde.plasma.kickerdash");
grid.currentConfigGroup = ["General"];
grid.writeConfig("icon", "view-app-grid-symbolic");
