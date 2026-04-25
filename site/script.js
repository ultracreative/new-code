const reveals = document.querySelectorAll(".reveal");

if (!("IntersectionObserver" in window)) {
  reveals.forEach((element) => element.classList.add("is-visible"));
}

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  },
  {
    threshold: 0.18,
    rootMargin: "0px 0px -6% 0px",
  },
);

if ("IntersectionObserver" in window) {
  reveals.forEach((element) => observer.observe(element));
}
