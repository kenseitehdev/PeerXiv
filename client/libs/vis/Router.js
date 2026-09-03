// Router.js

export function createRouter({ routes = {}, mode = "hash", target = "#app", notFound = null }) {
	let currentRoute = null;

	function render(path) {
		const mountPoint = document.querySelector(target);
		if (!mountPoint) return console.error("Router target not found:", target);

		const componentName = routes[path] ?? notFound;

		if (!componentName || typeof componentName !== "string") {
			mountPoint.innerHTML = "<h1>404 Not Found</h1>";
			currentRoute = path;
			return;
		}

		const el = document.createElement(componentName);
		mountPoint.innerHTML = "";
		mountPoint.appendChild(el);
		currentRoute = path;
	}

	function getPath() {
		return mode === "hash"
			? window.location.hash.slice(1) || "/"
			: window.location.pathname || "/";
	}

	function handleRouteChange() {
		const path = getPath();
		render(path);
	}

	function navigate(path) {
		if (mode === "hash") {
			window.location.hash = path;
		} else {
			history.pushState({}, "", path);
			handleRouteChange();
		}
	}

	function init() {
		if (mode === "hash") {
			window.addEventListener("hashchange", handleRouteChange);
		} else {
			window.addEventListener("popstate", handleRouteChange);
		}
		handleRouteChange();
	}

	return {
		init,
		navigate,
		get current() {
			return currentRoute;
		}
	};
}
