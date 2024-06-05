console.log('main.js loaded');

// Selecting DOM elements
const gunitInput = document.getElementById('lob-input');
const output = document.getElementById('output');
const dropdownID=document.getElementById('lob_select')
const gunitForm=document.getElementById('gunit-input')
let uploadBtn;

let gunitInputDisplayed = false;


function showGunitInput() {
    if (gunitInput && !gunitInputDisplayed) {
        gunitInput.style.display = 'block';
        if (output) {
            output.style.display = 'none';
        }
        gunitInputDisplayed = true;
    }
}
function showGunitInputAndForm() {
    if (gunitInput && gunitForm ) {
        gunitInput.style.display = 'block';
        gunitForm.style.display = 'block';
        if (output) {
            output.style.display = 'none';
        }
        gunitInputDisplayed = true;
    }
}

function autoSize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = (Math.min(textarea.scrollHeight, 300)) + 'px';
}
function copyToClipboard(id) {
          var textarea = document.getElementById(id);
          textarea.select();
          textarea.setSelectionRange(0, 99999); // For mobile devices

           try {
               var successful = document.execCommand('copy');
               var msg = successful ? 'successful' : 'unsuccessful';
               console.log('Copying text command was ' + msg);
            } catch (err) {
                console.error('Oops, unable to copy', err);
            }
        }



document.addEventListener("DOMContentLoaded", function() {
    document.querySelector('.menu a').addEventListener('click', (event) => {
        event.preventDefault();
        showGunitInput();
    });


dropdownID.addEventListener('change', function(event) {
    const selectedLOB = event.target.value;
    console.log("Selected Line of Business:", selectedLOB);
    if (selectedLOB && selectedLOB !== "") {
        console.log("entered Line of Business:", selectedLOB);
        document.getElementById("selected_lob").value = selectedLOB;

        showGunitInputAndForm();
    } else {
        console.log("did not enter Line of Business:", selectedLOB);
        gunitInput.style.display = 'none';
        gunitForm.style.display = 'none';
        gunitInputDisplayed = false;
    }
});


    uploadBtn = document.getElementById('upload-gunit');


    uploadBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (typeof initiateLoader === 'function') {
            initiateLoader();
        }
        document.querySelector('.upload-gunit').submit();
    });
});

